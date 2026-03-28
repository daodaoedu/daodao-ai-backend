import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Send, Trash2 } from 'lucide-react'
import { getUserQuota, listLLMModels, listSystemPrompts, playgroundChat } from '@/api/admin'
import type { ChatMessage, PlaygroundChatResponse } from '@/api/types'
import { useAuth } from '@/auth/AuthContext'

/** 將原始後端錯誤訊息轉為使用者友善文字 */
function _toFriendlyError(raw: string | null | undefined): string {
  if (!raw) return '發生未知錯誤，請重試'
  const s = raw.toLowerCase()
  if (s.includes('token 配額已用盡') || s.includes('quota exceeded'))
    return raw  // 已是友善訊息，直接顯示
  if (s.includes('credit balance') || s.includes('billing') || s.includes('payment'))
    return '模型 API 餘額不足，請至供應商後台儲值後再試'
  if (s.includes('quota') || s.includes('rate limit') || s.includes('rate_limit'))
    return '已達 API 使用限制，請稍後再試'
  if (s.includes('invalid_api_key') || s.includes('api key') || s.includes('authentication'))
    return 'API 金鑰無效或未設定，請確認後端設定'
  if (s.includes('model') && (s.includes('not found') || s.includes('does not exist')))
    return '指定模型不存在或已停用，請重新選擇'
  if (s.includes('context length') || s.includes('token limit') || s.includes('too long'))
    return '訊息超過模型 context 長度上限，請縮短內容'
  if (s.includes('timeout') || s.includes('timed out'))
    return '請求逾時，請稍後再試'
  if (s.includes('connection') || s.includes('network') || s.includes('unreachable'))
    return '無法連線至 AI 服務，請確認網路或後端狀態'
  // 其他：顯示簡短摘要（最多 80 字）
  return raw.length > 80 ? raw.slice(0, 80) + '…' : raw
}

/** token 用量百分比 → Tailwind 顏色 */
function _usageColor(used: number, limit: number): string {
  const pct = limit > 0 ? used / limit : 0
  if (pct >= 1) return 'bg-destructive'
  if (pct >= 0.8) return 'bg-yellow-400'
  return 'bg-primary'
}

export function PlaygroundPage() {
  const { adminInfo } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null)
  const [selectedPromptId, setSelectedPromptId] = useState<number | null>(null)
  const [isSending, setIsSending] = useState(false)
  const [lastStats, setLastStats] = useState<PlaygroundChatResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: models = [] } = useQuery({
    queryKey: ['llm-models', { is_active: true }],
    queryFn: () => listLLMModels({ is_active: true }).then((r) => r.data.data),
  })

  const { data: prompts = [] } = useQuery({
    queryKey: ['system-prompts', { is_active: true }],
    queryFn: () => listSystemPrompts({ is_active: true }).then((r) => r.data.data),
  })

  // 使用者 quota（有 adminId 才查）
  const { data: quotaData, refetch: refetchQuota } = useQuery({
    queryKey: ['admin-quota', adminInfo?.adminId],
    queryFn: () => getUserQuota(adminInfo!.adminId).then((r) => r.data.data),
    enabled: !!adminInfo?.adminId,
    staleTime: 30_000,  // 30 秒內不重新查
  })

  // 自動選第一個 model
  useEffect(() => {
    if (models.length > 0 && selectedModelId === null) {
      setSelectedModelId(models[0].id)
    }
  }, [models, selectedModelId])

  // 捲到最新訊息
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || !selectedModelId || isSending) return
    setError(null)

    const userMsg: ChatMessage = { role: 'user', content: input.trim() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsSending(true)

    try {
      const res = await playgroundChat({
        model_id: selectedModelId,
        system_prompt_id: selectedPromptId ?? undefined,
        message: userMsg.content,
      })

      // ── 後端 api_response_decorator 把所有錯誤都包成 HTTP 200 ──
      // 必須先判斷 success，否則 data 為 null 時存取 d.response 會拋 TypeError
      if (!res.data.success) {
        const errMsg =
          (res.data as { error?: { message?: string } }).error?.message ?? '發生未知錯誤'
        setError(_toFriendlyError(errMsg))
        setMessages((prev) => prev.slice(0, -1))
        return
      }

      const d = res.data.data
      setLastStats(d)
      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: d.response,
        meta: {
          input_tokens: d.input_tokens,
          output_tokens: d.output_tokens,
          cost_usd: d.cost_usd,
          latency_ms: d.latency_ms,
          model_used: d.model_used,
        },
      }
      setMessages((prev) => [...prev, assistantMsg])
      // 送出後重新整理 quota 顯示
      refetchQuota()
    } catch (err: unknown) {
      // HTTP 4xx/5xx（理論上 decorator 會攔截，但保留作為備用）
      const raw =
        (err as { response?: { data?: { error?: { message?: string }; detail?: string } } })
          ?.response?.data?.error?.message ??
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err instanceof Error ? err.message : null)

      const friendly = _toFriendlyError(raw)
      setError(friendly)
      setMessages((prev) => prev.slice(0, -1)) // 移除 user 訊息
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const monthlyUsed = quotaData?.current_month_tokens_used ?? 0
  const monthlyLimit = quotaData?.quota?.monthly_token_limit ?? 0
  const dailyLimit = quotaData?.quota?.daily_token_limit ?? null

  return (
    <div className="flex h-full">
      {/* ── 左側設定欄 ── */}
      <aside className="w-64 shrink-0 border-r border-border bg-card flex flex-col gap-4 p-4">
        <h2 className="font-semibold text-sm text-foreground">設定</h2>

        {/* Model 選擇 */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">LLM 模型</label>
          <select
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={selectedModelId ?? ''}
            onChange={(e) => setSelectedModelId(Number(e.target.value))}
          >
            <option value="" disabled>選擇模型…</option>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name ?? `${m.provider}/${m.model_name}`}
              </option>
            ))}
          </select>
        </div>

        {/* System Prompt 選擇 */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">System Prompt</label>
          <select
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={selectedPromptId ?? ''}
            onChange={(e) =>
              setSelectedPromptId(e.target.value === '' ? null : Number(e.target.value))
            }
          >
            <option value="">不使用</option>
            {prompts.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* 清除對話 */}
        <button
          onClick={() => { setMessages([]); setLastStats(null); setError(null) }}
          className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <Trash2 className="h-4 w-4" />
          清除對話
        </button>

        {/* 使用者資訊 & Quota */}
        {adminInfo && (
          <div className="mt-auto border-t border-border pt-4 space-y-3">
            <div>
              <p className="text-xs font-medium text-muted-foreground">目前使用者</p>
              <p className="text-sm font-medium text-foreground truncate">
                {adminInfo.adminNickname ?? `Admin #${adminInfo.adminId}`}
              </p>
              <p className="text-xs text-muted-foreground">ID: {adminInfo.adminId}</p>
            </div>

            {quotaData ? (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Token 配額（本月）</p>
                {quotaData.quota !== null ? (
                  <>
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>{monthlyUsed.toLocaleString()}</span>
                      <span>{monthlyLimit.toLocaleString()}</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${_usageColor(monthlyUsed, monthlyLimit)}`}
                        style={{ width: `${Math.min(100, (monthlyUsed / monthlyLimit) * 100)}%` }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground text-right">
                      剩餘 {Math.max(0, monthlyLimit - monthlyUsed).toLocaleString()} tokens
                    </p>
                    {dailyLimit !== null && (
                      <p className="text-xs text-muted-foreground">
                        日限制：{dailyLimit.toLocaleString()} tokens
                      </p>
                    )}
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    已用 {monthlyUsed.toLocaleString()} tokens（無配額限制）
                  </p>
                )}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">配額載入中…</p>
            )}
          </div>
        )}
      </aside>

      {/* ── 中央聊天區 ── */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* 訊息列表 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
              選擇模型後輸入訊息開始測試
            </div>
          )}
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[75%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${msg.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                  }`}
              >
                {msg.content}
                {msg.role === 'assistant' && msg.meta && (
                  <div className="mt-1 text-xs opacity-60">
                    {(msg.meta.input_tokens + msg.meta.output_tokens).toLocaleString()} tokens
                    {msg.meta.cost_usd > 0 && ` · $${msg.meta.cost_usd.toFixed(6)}`}
                    {` · ${msg.meta.latency_ms}ms`}
                  </div>
                )}
              </div>
            </div>
          ))}
          {isSending && (
            <div className="flex justify-start">
              <div className="rounded-lg bg-muted px-4 py-2 text-sm text-muted-foreground">
                生成中…
              </div>
            </div>
          )}
          {error && (
            <div className="rounded-md bg-destructive/10 border border-destructive/20 px-4 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* 輸入區 */}
        <div className="border-t border-border p-4">
          <div className="flex gap-2 items-end">
            <textarea
              rows={3}
              className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="輸入訊息… (Enter 送出，Shift+Enter 換行)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isSending || !selectedModelId}
            />
            <button
              onClick={handleSend}
              disabled={isSending || !input.trim() || !selectedModelId}
              className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="h-4 w-4" />
              送出
            </button>
          </div>
        </div>
      </div>

      {/* ── 右側統計欄 ── */}
      <aside className="w-52 shrink-0 border-l border-border bg-card p-4 space-y-4">
        <h2 className="font-semibold text-sm text-foreground">最後一次統計</h2>
        {lastStats ? (
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">模型</dt>
              <dd className="font-medium text-foreground break-all">{lastStats.model_used}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Input tokens</dt>
              <dd className="font-medium text-foreground">{lastStats.input_tokens.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Output tokens</dt>
              <dd className="font-medium text-foreground">{lastStats.output_tokens.toLocaleString()}</dd>
            </div>
            {lastStats.cost_usd > 0 && (
              <div>
                <dt className="text-xs text-muted-foreground">Cost (USD)</dt>
                <dd className="font-medium text-foreground">${lastStats.cost_usd.toFixed(6)}</dd>
              </div>
            )}
            <div>
              <dt className="text-xs text-muted-foreground">Latency</dt>
              <dd className="font-medium text-foreground">{lastStats.latency_ms} ms</dd>
            </div>
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground">送出第一則訊息後顯示</p>
        )}
      </aside>
    </div>
  )
}

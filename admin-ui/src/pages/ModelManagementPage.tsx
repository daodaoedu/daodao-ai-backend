import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listLLMModels } from '@/api/admin'
import type { LLMModel } from '@/api/types'

export function ModelManagementPage() {
  const [selected, setSelected] = useState<LLMModel | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['llm-models'],
    queryFn: () => listLLMModels().then((r) => r.data.data),
  })

  const costFields = [
    { key: 'input_cost_per_1m', label: 'Input Cost / 1M tokens' },
    { key: 'output_cost_per_1m', label: 'Output Cost / 1M tokens' },
    { key: 'cached_input_cost_per_1m', label: 'Cached Input Cost / 1M tokens' },
  ] as const

  return (
    <div className="flex gap-6 h-full">
      {/* ── 左側列表 ── */}
      <div className="w-80 shrink-0 space-y-2">
        <h1 className="text-xl font-bold">LLM Models</h1>
        <p className="text-xs text-muted-foreground">模型由後端設定自動匯入，無法在此新增或刪除。</p>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">載入中...</p>
        ) : (
          <div className="space-y-1">
            {(data ?? []).map((m) => (
              <button
                key={m.id}
                onClick={() => setSelected(m)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors
                  ${selected?.id === m.id
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:bg-accent'
                  }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium truncate">{m.display_name ?? m.model_name}</span>
                  <span
                    className={`ml-1 shrink-0 rounded px-1.5 py-0.5 text-xs ${
                      m.is_active
                        ? 'bg-green-100 text-green-700'
                        : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {m.is_active ? 'active' : 'inactive'}
                  </span>
                </div>
                <div className="mt-0.5 flex gap-2 text-xs text-muted-foreground">
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 text-primary">{m.provider}</span>
                  <span className="truncate">{m.model_name}</span>
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  in: ${m.input_cost_per_1m} / out: ${m.output_cost_per_1m}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── 右側唯讀詳情 ── */}
      {selected && (
        <div className="flex-1 space-y-6">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold">{selected.display_name ?? selected.model_name}</h2>
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
                selected.is_active
                  ? 'bg-green-100 text-green-700'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              {selected.is_active ? 'active' : 'inactive'}
            </span>
          </div>

          {/* 基本資訊 */}
          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <h3 className="text-sm font-medium text-muted-foreground">基本資訊</h3>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground mb-0.5">Provider</dt>
                <dd>
                  <span className="rounded bg-primary/10 px-2 py-0.5 text-sm text-primary font-medium">
                    {selected.provider}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground mb-0.5">Model Name</dt>
                <dd className="font-mono text-foreground">{selected.model_name}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-muted-foreground mb-0.5">Display Name</dt>
                <dd className="text-foreground">{selected.display_name ?? '—'}</dd>
              </div>
            </dl>
          </section>

          {/* 費率 */}
          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <h3 className="text-sm font-medium text-muted-foreground">費率（USD per 1M tokens）</h3>
            <dl className="grid grid-cols-3 gap-x-6 gap-y-3 text-sm">
              {costFields.map(({ key, label }) => (
                <div key={key}>
                  <dt className="text-xs text-muted-foreground mb-0.5">{label}</dt>
                  <dd className="font-mono text-foreground">${selected[key]}</dd>
                </div>
              ))}
            </dl>
          </section>

          {/* 備註 & 時間 */}
          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <h3 className="text-sm font-medium text-muted-foreground">其他</h3>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground mb-0.5">Notes</dt>
                <dd className="whitespace-pre-wrap text-foreground">{selected.notes || '—'}</dd>
              </div>
              <div className="grid grid-cols-2 gap-x-6">
                <div>
                  <dt className="text-xs text-muted-foreground mb-0.5">建立時間</dt>
                  <dd className="text-foreground">
                    {new Date(selected.created_at).toLocaleString('zh-TW')}
                  </dd>
                </div>
                {selected.updated_at && (
                  <div>
                    <dt className="text-xs text-muted-foreground mb-0.5">更新時間</dt>
                    <dd className="text-foreground">
                      {new Date(selected.updated_at).toLocaleString('zh-TW')}
                    </dd>
                  </div>
                )}
              </div>
            </dl>
          </section>
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listUsers, upsertUserQuota } from '@/api/admin'
import type { UserWithQuota } from '@/api/types'

const LIMIT = 50

interface QuotaForm {
  monthly_token_limit: string
  daily_token_limit: string
}

export function UserQuotasPage() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [editing, setEditing] = useState<UserWithQuota | null>(null)
  const [quotaForm, setQuotaForm] = useState<QuotaForm>({ monthly_token_limit: '1000000', daily_token_limit: '' })

  const { data, isLoading } = useQuery({
    queryKey: ['admin-users', search, offset],
    queryFn: () => listUsers({ limit: LIMIT, offset, search: search || undefined }).then((r) => r.data),
  })

  const users = data?.data ?? []
  const pagination = data?.pagination

  const upsertMut = useMutation({
    mutationFn: ({ userId, form }: { userId: number; form: QuotaForm }) =>
      upsertUserQuota(userId, {
        monthly_token_limit: parseInt(form.monthly_token_limit, 10),
        daily_token_limit: form.daily_token_limit ? parseInt(form.daily_token_limit, 10) : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      setEditing(null)
    },
  })

  const openEdit = (u: UserWithQuota) => {
    setQuotaForm({
      monthly_token_limit: u.quota ? String(u.quota.monthly_token_limit) : '100000',
      daily_token_limit: u.quota?.daily_token_limit ? String(u.quota.daily_token_limit) : '',
    })
    setEditing(u)
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">User Token Quotas</h1>

      <div className="flex gap-2">
        <input
          placeholder="搜尋 nickname / mongo_id"
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring w-72"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOffset(0) }}
        />
      </div>

      <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted text-muted-foreground">
              {['ID', 'Nickname', 'Mongo ID', 'Role', '本月使用 Tokens', 'Monthly Limit', 'Daily Limit', '操作'].map((h) => (
                <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={8} className="px-4 py-6 text-center text-muted-foreground">載入中...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-6 text-center text-muted-foreground">無資料</td></tr>
            ) : users.map((u) => (
              <tr key={u.id} className="border-b border-border hover:bg-accent transition-colors">
                <td className="px-4 py-2 font-mono text-xs">{u.id}</td>
                <td className="px-4 py-2 font-medium">{u.nickname ?? '-'}</td>
                <td className="px-4 py-2 font-mono text-xs truncate max-w-[120px]">{u.mongo_id ?? '-'}</td>
                <td className="px-4 py-2">{u.role_id ?? '-'}</td>
                <td className="px-4 py-2">
                  <span className={`font-mono ${u.current_month_tokens_used > 0 ? 'text-foreground' : 'text-muted-foreground'}`}>
                    {u.current_month_tokens_used.toLocaleString()}
                  </span>
                </td>
                <td className="px-4 py-2">
                  {u.quota ? (
                    <span className="font-mono">{u.quota.monthly_token_limit.toLocaleString()}</span>
                  ) : (
                    <span className="text-muted-foreground text-xs">未設定</span>
                  )}
                </td>
                <td className="px-4 py-2">
                  {u.quota?.daily_token_limit ? (
                    <span className="font-mono">{u.quota.daily_token_limit.toLocaleString()}</span>
                  ) : (
                    <span className="text-muted-foreground text-xs">不限</span>
                  )}
                </td>
                <td className="px-4 py-2">
                  <button
                    onClick={() => openEdit(u)}
                    className="rounded border border-border px-2 py-1 text-xs hover:bg-accent transition-colors"
                  >
                    設定 Quota
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pagination && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>共 {pagination.total_count} 位用戶</span>
          <div className="flex gap-2">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - LIMIT))}
              className="rounded border border-border px-3 py-1 hover:bg-accent disabled:opacity-40 transition-colors"
            >
              上一頁
            </button>
            <button
              disabled={!pagination.has_next}
              onClick={() => setOffset(offset + LIMIT)}
              className="rounded border border-border px-3 py-1 hover:bg-accent disabled:opacity-40 transition-colors"
            >
              下一頁
            </button>
          </div>
        </div>
      )}

      {/* Edit modal */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-lg">
            <h3 className="mb-4 font-semibold">設定 Quota — {editing.nickname ?? editing.mongo_id ?? `User #${editing.id}`}</h3>

            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Monthly Token Limit</label>
                <input
                  type="number"
                  min="0"
                  className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
                  value={quotaForm.monthly_token_limit}
                  onChange={(e) => setQuotaForm((f) => ({ ...f, monthly_token_limit: e.target.value }))}
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium">Daily Token Limit（留空 = 不限）</label>
                <input
                  type="number"
                  min="0"
                  placeholder="不設每日上限"
                  className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
                  value={quotaForm.daily_token_limit}
                  onChange={(e) => setQuotaForm((f) => ({ ...f, daily_token_limit: e.target.value }))}
                />
              </div>
            </div>

            <div className="mt-5 flex gap-2 justify-end">
              <button
                className="rounded border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-accent transition-colors"
                onClick={() => setEditing(null)}
              >
                取消
              </button>
              <button
                className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                onClick={() => upsertMut.mutate({ userId: editing.id, form: quotaForm })}
                disabled={upsertMut.isPending}
              >
                {upsertMut.isPending ? '儲存中...' : '儲存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

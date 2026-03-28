import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listQueryLogs, type QueryLogFilters } from '@/api/admin'
import type { AIQueryLog } from '@/api/types'
import { format } from 'date-fns'

const LIMIT = 50

export function QueryLogsPage() {
  const [filters, setFilters] = useState<QueryLogFilters>({})
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<AIQueryLog | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['query-logs', filters, offset],
    queryFn: () => listQueryLogs({ ...filters, limit: LIMIT, offset }).then((r) => r.data),
  })

  const logs = data?.data ?? []
  const pagination = data?.pagination

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">AI 查詢日誌</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {(['backend', 'context', 'status'] as const).map((field) => (
          <input
            key={field}
            placeholder={field}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            value={(filters as Record<string, string>)[field] ?? ''}
            onChange={(e) => {
              setFilters((f) => ({ ...f, [field]: e.target.value || undefined }))
              setOffset(0)
            }}
          />
        ))}
        <input
          type="date"
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          value={filters.date_from ?? ''}
          onChange={(e) => { setFilters((f) => ({ ...f, date_from: e.target.value || undefined })); setOffset(0) }}
        />
        <input
          type="date"
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          value={filters.date_to ?? ''}
          onChange={(e) => { setFilters((f) => ({ ...f, date_to: e.target.value || undefined })); setOffset(0) }}
        />
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted text-muted-foreground">
              {['ID', 'Backend', 'Context', 'User', 'Tokens', 'Cost (USD)', 'Latency', 'Status', '時間'].map((h) => (
                <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={9} className="px-4 py-6 text-center text-muted-foreground">載入中...</td></tr>
            ) : logs.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-6 text-center text-muted-foreground">無資料</td></tr>
            ) : logs.map((log) => (
              <tr
                key={log.id}
                className="border-b border-border hover:bg-accent cursor-pointer transition-colors"
                onClick={() => setSelected(selected?.id === log.id ? null : log)}
              >
                <td className="px-4 py-2 font-mono text-xs">{log.id}</td>
                <td className="px-4 py-2"><span className="rounded bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">{log.backend}</span></td>
                <td className="px-4 py-2 text-muted-foreground">{log.context ?? '-'}</td>
                <td className="px-4 py-2 font-mono text-xs truncate max-w-[100px]">{log.user_id ?? '-'}</td>
                <td className="px-4 py-2">{log.total_tokens?.toLocaleString() ?? '-'}</td>
                <td className="px-4 py-2">{log.cost_usd ? `$${Number(log.cost_usd).toFixed(5)}` : '-'}</td>
                <td className="px-4 py-2">{log.latency_ms ? `${log.latency_ms}ms` : '-'}</td>
                <td className="px-4 py-2">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${log.status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {log.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-xs text-muted-foreground whitespace-nowrap">
                  {format(new Date(log.created_at), 'MM-dd HH:mm:ss')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Detail panel */}
      {selected && (
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="mb-3 font-semibold">Log #{selected.id} 詳情</h3>
          <pre className="overflow-x-auto rounded bg-muted p-3 text-xs">
            {JSON.stringify(selected, null, 2)}
          </pre>
        </div>
      )}

      {/* Pagination */}
      {pagination && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>共 {pagination.total_count} 筆</span>
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
    </div>
  )
}

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { getDashboardStats } from '@/api/admin'
import { format, subDays } from 'date-fns'

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  )
}

export function DashboardPage() {
  const [dateFrom] = useState(() => format(subDays(new Date(), 6), 'yyyy-MM-dd'))
  const [dateTo] = useState(() => format(new Date(), 'yyyy-MM-dd'))

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard', dateFrom, dateTo],
    queryFn: () => getDashboardStats(dateFrom, dateTo).then((r) => r.data.data),
    refetchInterval: 300_000,
  })

  if (isLoading) return <div className="text-muted-foreground">載入中...</div>
  if (error || !data) return <div className="text-destructive">載入失敗</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <p className="text-sm text-muted-foreground">{dateFrom} ~ {dateTo}</p>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="總費用 (USD)" value={`$${Number(data.total_cost_usd).toFixed(4)}`} />
        <StatCard label="總查詢次數" value={data.total_queries.toLocaleString()} />
        <StatCard label="Input Tokens" value={data.total_input_tokens.toLocaleString()} />
        <StatCard label="Output Tokens" value={data.total_output_tokens.toLocaleString()} />
      </div>

      {/* By backend */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h2 className="mb-4 font-semibold">各 Backend 費用</h2>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data.by_backend}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="backend" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v: number) => [`$${Number(v).toFixed(5)}`, '費用']} />
            <Bar dataKey="cost_usd" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Daily trend */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h2 className="mb-4 font-semibold">每日查詢趨勢</h2>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data.daily_series}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="query_count" stroke="hsl(var(--primary))" name="查詢次數" dot={false} />
            <Line yAxisId="right" type="monotone" dataKey="total_tokens" stroke="#22c55e" name="Tokens" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

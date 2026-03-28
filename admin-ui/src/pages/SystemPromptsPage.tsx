import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listSystemPrompts,
  createSystemPrompt,
  updateSystemPrompt,
  deleteSystemPrompt,
} from '@/api/admin'
import type { SystemPrompt } from '@/api/types'

export function SystemPromptsPage() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<SystemPrompt | null>(null)
  const [isNew, setIsNew] = useState(false)
  const [form, setForm] = useState({ name: '', content: '', is_active: false })

  const { data, isLoading } = useQuery({
    queryKey: ['system-prompts'],
    queryFn: () => listSystemPrompts({ limit: 100 }).then((r) => r.data.data),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['system-prompts'] })

  const createMut = useMutation({
    mutationFn: createSystemPrompt,
    onSuccess: () => { invalidate(); setIsNew(false) },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof updateSystemPrompt>[1] }) =>
      updateSystemPrompt(id, data),
    onSuccess: () => { invalidate(); setSelected(null) },
  })

  const deleteMut = useMutation({
    mutationFn: deleteSystemPrompt,
    onSuccess: () => { invalidate(); setSelected(null) },
  })

  const openNew = () => {
    setForm({ name: '', content: '', is_active: false })
    setSelected(null)
    setIsNew(true)
  }

  const openEdit = (p: SystemPrompt) => {
    setForm({ name: p.name, content: p.content, is_active: p.is_active })
    setSelected(p)
    setIsNew(false)
  }

  return (
    <div className="flex gap-6 h-full">
      {/* List */}
      <div className="w-72 shrink-0 space-y-2">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">System Prompts</h1>
          <button
            onClick={openNew}
            className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            + 新增
          </button>
        </div>
        {isLoading ? <p className="text-sm text-muted-foreground">載入中...</p> : (
          <div className="space-y-1">
            {(data ?? []).map((p) => (
              <button
                key={p.id}
                onClick={() => openEdit(p)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors
                  ${selected?.id === p.id ? 'border-primary bg-primary/5' : 'border-border hover:bg-accent'}`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium truncate">{p.name}</span>
                  {p.is_active && <span className="ml-1 shrink-0 rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">active</span>}
                </div>
                <div className="mt-0.5 flex gap-2 text-xs text-muted-foreground">
                  <span>v{p.version}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Editor */}
      {(isNew || selected) && (
        <div className="flex-1 space-y-4">
          <h2 className="font-semibold">{isNew ? '新增 Prompt' : `編輯：${selected!.name}`}</h2>
          <div className="grid grid-cols-2 gap-3">
            {['name'].map((field) => (
              <div key={field}>
                <label className="mb-1 block text-sm font-medium">{field}</label>
                <input
                  className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  value={(form as unknown as Record<string, string>)[field]}
                  onChange={(e) => setForm((f) => ({ ...f, [field]: e.target.value }))}
                />
              </div>
            ))}
            <div className="flex items-center gap-2 pt-5">
              <input
                type="checkbox"
                id="is_active"
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                className="h-4 w-4"
              />
              <label htmlFor="is_active" className="text-sm font-medium">is_active</label>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">content</label>
            <textarea
              rows={16}
              className="w-full rounded border border-input bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              value={form.content}
              onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
            />
          </div>
          <div className="flex gap-2">
            <button
              className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              onClick={() => {
                const payload = { name: form.name, content: form.content, is_active: form.is_active }
                if (isNew) createMut.mutate(payload)
                else updateMut.mutate({ id: selected!.id, data: payload })
              }}
            >
              {isNew ? '建立' : '儲存'}
            </button>
            {selected && (
              <button
                className="rounded border border-destructive px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/5 transition-colors"
                onClick={() => { if (confirm('確定刪除？')) deleteMut.mutate(selected.id) }}
              >
                刪除
              </button>
            )}
            <button
              className="rounded border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-accent transition-colors"
              onClick={() => { setSelected(null); setIsNew(false) }}
            >
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

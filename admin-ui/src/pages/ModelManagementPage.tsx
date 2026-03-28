import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listLLMModels, createLLMModel, updateLLMModel, deleteLLMModel } from '@/api/admin'
import type { LLMModel, LLMModelCreate } from '@/api/types'

const emptyForm: LLMModelCreate = {
  provider: '',
  model_name: '',
  display_name: '',
  is_active: true,
  input_cost_per_1m: '0',
  output_cost_per_1m: '0',
  cached_input_cost_per_1m: '0',
  notes: '',
}

export function ModelManagementPage() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<LLMModel | null>(null)
  const [isNew, setIsNew] = useState(false)
  const [form, setForm] = useState<LLMModelCreate>(emptyForm)

  const { data, isLoading } = useQuery({
    queryKey: ['llm-models'],
    queryFn: () => listLLMModels().then((r) => r.data.data),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['llm-models'] })

  const createMut = useMutation({
    mutationFn: createLLMModel,
    onSuccess: () => { invalidate(); setIsNew(false) },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<LLMModelCreate> }) =>
      updateLLMModel(id, data),
    onSuccess: () => { invalidate(); setSelected(null) },
  })

  const deleteMut = useMutation({
    mutationFn: deleteLLMModel,
    onSuccess: () => { invalidate(); setSelected(null) },
  })

  const openNew = () => {
    setForm(emptyForm)
    setSelected(null)
    setIsNew(true)
  }

  const openEdit = (m: LLMModel) => {
    setForm({
      provider: m.provider,
      model_name: m.model_name,
      display_name: m.display_name ?? '',
      is_active: m.is_active,
      input_cost_per_1m: m.input_cost_per_1m,
      output_cost_per_1m: m.output_cost_per_1m,
      cached_input_cost_per_1m: m.cached_input_cost_per_1m,
      notes: m.notes ?? '',
    })
    setSelected(m)
    setIsNew(false)
  }

  const costFields = [
    { key: 'input_cost_per_1m', label: 'Input Cost / 1M tokens (USD)' },
    { key: 'output_cost_per_1m', label: 'Output Cost / 1M tokens (USD)' },
    { key: 'cached_input_cost_per_1m', label: 'Cached Input Cost / 1M tokens (USD)' },
  ] as const

  return (
    <div className="flex gap-6 h-full">
      {/* List */}
      <div className="w-80 shrink-0 space-y-2">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">LLM Models</h1>
          <button
            onClick={openNew}
            className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            + 新增
          </button>
        </div>
        {isLoading ? <p className="text-sm text-muted-foreground">載入中...</p> : (
          <div className="space-y-1">
            {(data ?? []).map((m) => (
              <button
                key={m.id}
                onClick={() => openEdit(m)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors
                  ${selected?.id === m.id ? 'border-primary bg-primary/5' : 'border-border hover:bg-accent'}`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium truncate">{m.display_name ?? m.model_name}</span>
                  {m.is_active && (
                    <span className="ml-1 shrink-0 rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">active</span>
                  )}
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

      {/* Editor */}
      {(isNew || selected) && (
        <div className="flex-1 space-y-4">
          <h2 className="font-semibold">{isNew ? '新增 LLM Model' : `編輯：${selected!.display_name ?? selected!.model_name}`}</h2>

          <div className="grid grid-cols-2 gap-3">
            {(['provider', 'model_name', 'display_name'] as const).map((field) => (
              <div key={field}>
                <label className="mb-1 block text-sm font-medium">{field}</label>
                <input
                  className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  value={(form[field] as string) ?? ''}
                  onChange={(e) => setForm((f) => ({ ...f, [field]: e.target.value }))}
                />
              </div>
            ))}
            <div className="flex items-center gap-2 pt-5">
              <input
                type="checkbox"
                id="model_is_active"
                checked={form.is_active ?? true}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                className="h-4 w-4"
              />
              <label htmlFor="model_is_active" className="text-sm font-medium">is_active</label>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            {costFields.map(({ key, label }) => (
              <div key={key}>
                <label className="mb-1 block text-sm font-medium">{label}</label>
                <input
                  type="number"
                  step="0.000001"
                  min="0"
                  className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
                  value={(form[key] as string) ?? '0'}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">notes</label>
            <textarea
              rows={4}
              className="w-full rounded border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              value={form.notes ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </div>

          <div className="flex gap-2">
            <button
              className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              onClick={() => {
                const payload: LLMModelCreate = {
                  ...form,
                  display_name: form.display_name || undefined,
                  notes: form.notes || undefined,
                }
                if (isNew) createMut.mutate(payload)
                else updateMut.mutate({ id: selected!.id, data: payload })
              }}
            >
              {isNew ? '建立' : '儲存'}
            </button>
            {selected && (
              <button
                className="rounded border border-destructive px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/5 transition-colors"
                onClick={() => { if (confirm('確定刪除此模型？')) deleteMut.mutate(selected.id) }}
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

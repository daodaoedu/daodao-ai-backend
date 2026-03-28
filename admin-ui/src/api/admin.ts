import apiClient from './client'
import type {
  AdminPingData,
  AIQueryLog,
  ApiResponse,
  DashboardStats,
  LLMModel,
  LLMModelCreate,
  OffsetPagination,
  PlaygroundChatRequest,
  PlaygroundChatResponse,
  SystemPrompt,
  SystemPromptCreate,
  SystemPromptUpdate,
  UserQuota,
  UserWithQuota,
} from './types'

// ── Auth ──────────────────────────────────────────────────
export const ping = () =>
  apiClient.get<ApiResponse<AdminPingData>>('/api/v1/admin/ping')

// ── Dashboard ─────────────────────────────────────────────
export const getDashboardStats = (dateFrom?: string, dateTo?: string) =>
  apiClient.get<ApiResponse<DashboardStats>>('/api/v1/admin/dashboard/stats', {
    params: { date_from: dateFrom, date_to: dateTo },
  })

// ── System Prompts ────────────────────────────────────────
export const listSystemPrompts = (params?: {
  is_active?: boolean
  limit?: number
  offset?: number
}) =>
  apiClient.get<ApiResponse<SystemPrompt[]>>('/api/v1/admin/system-prompts', {
    params,
  })

export const getSystemPrompt = (id: number) =>
  apiClient.get<ApiResponse<SystemPrompt>>(`/api/v1/admin/system-prompts/${id}`)

export const createSystemPrompt = (data: SystemPromptCreate) =>
  apiClient.post<ApiResponse<SystemPrompt>>('/api/v1/admin/system-prompts', data)

export const updateSystemPrompt = (id: number, data: SystemPromptUpdate) =>
  apiClient.put<ApiResponse<SystemPrompt>>(`/api/v1/admin/system-prompts/${id}`, data)

export const deleteSystemPrompt = (id: number) =>
  apiClient.delete<ApiResponse<{ deleted: boolean; id: number }>>(
    `/api/v1/admin/system-prompts/${id}`
  )

// ── LLM Models ────────────────────────────────────────────
export const listLLMModels = (params?: { provider?: string; is_active?: boolean }) =>
  apiClient.get<ApiResponse<LLMModel[]>>('/api/v1/admin/llm-models', { params })

export const createLLMModel = (data: LLMModelCreate) =>
  apiClient.post<ApiResponse<LLMModel>>('/api/v1/admin/llm-models', data)

export const updateLLMModel = (id: number, data: Partial<LLMModelCreate>) =>
  apiClient.put<ApiResponse<LLMModel>>(`/api/v1/admin/llm-models/${id}`, data)

export const deleteLLMModel = (id: number) =>
  apiClient.delete<ApiResponse<{ deleted: boolean; id: number }>>(
    `/api/v1/admin/llm-models/${id}`
  )

// ── AI Query Logs ─────────────────────────────────────────
export interface QueryLogFilters {
  backend?: string
  context?: string
  user_id?: number
  status?: string
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
}

export const listQueryLogs = (params?: QueryLogFilters) =>
  apiClient.get<ApiResponse<AIQueryLog[]> & { pagination: OffsetPagination }>(
    '/api/v1/admin/query-logs',
    { params }
  )

export const getQueryLog = (id: number) =>
  apiClient.get<ApiResponse<AIQueryLog>>(`/api/v1/admin/query-logs/${id}`)

// ── User Quotas ───────────────────────────────────────────
export const listUsers = (params?: {
  limit?: number
  offset?: number
  search?: string
}) =>
  apiClient.get<ApiResponse<UserWithQuota[]>>('/api/v1/admin/users', { params })

export const getUserQuota = (userId: number) =>
  apiClient.get<
    ApiResponse<{
      user_id: number
      current_month_tokens_used: number
      quota: UserQuota | null
    }>
  >(`/api/v1/admin/users/${userId}/quota`)

// ── Playground ────────────────────────────────────────────
export const playgroundChat = (data: PlaygroundChatRequest) =>
  apiClient.post<ApiResponse<PlaygroundChatResponse>>('/api/v1/admin/playground/chat', data)

// ── User Quotas ───────────────────────────────────────────
export const upsertUserQuota = (
  userId: number,
  data: {
    monthly_token_limit: number
    daily_token_limit?: number | null
    quota_month?: number
  }
) => apiClient.put<ApiResponse<UserQuota>>(`/api/v1/admin/users/${userId}/quota`, data)

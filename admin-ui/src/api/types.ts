// ── API 回應外殼 ──────────────────────────────────────────
export interface ApiResponse<T> {
  success: boolean
  data: T
  error: null | { code: string; message: string }
  pagination: null | OffsetPagination
  cacheHit: boolean
  processingTime: number
  timestamp: string
  requestId: string
}

export interface OffsetPagination {
  total_count: number
  limit: number
  offset: number
  has_next: boolean
}

// ── Auth ──────────────────────────────────────────────────
export interface AdminPingData {
  status: string
  admin_id: number
  admin_mongo_id: string | null
  nickname: string | null
}

// ── Dashboard ─────────────────────────────────────────────
export interface BackendStat {
  backend: string
  query_count: number
  cost_usd: string
  total_tokens: number
}

export interface DailyStatPoint {
  date: string
  cost_usd: string
  query_count: number
  total_tokens: number
}

export interface DashboardStats {
  total_cost_usd: string
  total_queries: number
  total_input_tokens: number
  total_output_tokens: number
  by_backend: BackendStat[]
  daily_series: DailyStatPoint[]
}

// ── System Prompts ────────────────────────────────────────
export interface SystemPrompt {
  id: number
  name: string
  content: string
  is_active: boolean
  version: number
  created_by: number | null
  updated_by: number | null
  created_at: string
  updated_at: string | null
}

export interface SystemPromptCreate {
  name: string
  content: string
  is_active?: boolean
}

export interface SystemPromptUpdate {
  name?: string
  content?: string
  is_active?: boolean
}

// ── LLM Models ────────────────────────────────────────────
export interface LLMModel {
  id: number
  provider: string
  model_name: string
  display_name: string | null
  is_active: boolean
  input_cost_per_1m: string
  output_cost_per_1m: string
  cached_input_cost_per_1m: string
  notes: string | null
  created_at: string
  updated_at: string | null
}

export interface LLMModelCreate {
  provider: string
  model_name: string
  display_name?: string
  is_active?: boolean
  input_cost_per_1m?: string
  output_cost_per_1m?: string
  cached_input_cost_per_1m?: string
  notes?: string
}

// ── AI Query Logs ─────────────────────────────────────────
export interface AIQueryLog {
  id: number
  request_id: string
  backend: string
  model_name: string | null
  context: string | null
  user_id: number | null
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  cost_usd: string | null
  latency_ms: number | null
  status: string
  error_message: string | null
  prompt_chars: number | null
  created_at: string
  usage_detail?: Record<string, unknown>
}

// ── Playground ────────────────────────────────────────────
export interface PlaygroundChatRequest {
  model_id: number
  system_prompt_id?: number | null
  message: string
}

export interface PlaygroundChatResponse {
  response: string
  model_used: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  latency_ms: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  meta?: {
    input_tokens: number
    output_tokens: number
    cost_usd: number
    latency_ms: number
    model_used: string
  }
}

// ── User Quotas ───────────────────────────────────────────
export interface UserQuota {
  id: number
  user_id: number
  monthly_token_limit: number
  daily_token_limit: number | null
  quota_month: number | null
  created_at: string
  updated_at: string | null
}

export interface UserWithQuota {
  id: number
  mongo_id: string | null
  nickname: string | null
  external_id: string | null
  role_id: number | null
  current_month_tokens_used: number
  quota: UserQuota | null
}

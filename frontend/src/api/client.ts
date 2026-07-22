const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export type User = { id: string; email: string; username: string; risk_profile: string; created_at: string }
export type AuthResult = { access_token: string; token_type: string; user: User }
export type ResearchJob = {
  id: string; stock_code: string; depth: string; risk_profile: string; status: string;
  progress: number; error: string; created_at: string; started_at: string | null; completed_at: string | null
}
export type StoredPosition = { id: string; stock_code: string; stock_name: string; quantity: number; average_cost: string }
export type Position = StoredPosition & {
  cost_value: string; market_price: string | null; market_value: string | null;
  unrealized_pnl: string | null; pnl_pct: string | null; quote_time: string | null;
  is_realtime: boolean; market_source: string | null; market_error: string | null
}
export type ResearchReport = { id: string; job_id: string; action: string; confidence: number; rank_score: number; summary: string; report_payload: Record<string, unknown>; created_at: string }
export type ChatMessage = { id: string; role: string; content: string; tool_name: string | null; tool_payload: Record<string, unknown> | null; created_at: string }
export type Conversation = { id: string; title: string; created_at: string; updated_at: string; messages: ChatMessage[] }
export type MemoryItem = {
  id: string; memory_type: string; memory_key: string; memory_value: unknown; confidence: number;
  status: string; source_message_id: string | null; created_at: string; updated_at: string
}
export type KnowledgeDocument = {
  id: string; filename: string; title: string; mime_type: string; file_size: number;
  stock_code: string | null; source_type: KnowledgeSourceType; status: string; chunk_count: number; error: string;
  created_at: string; updated_at: string
}
export type KnowledgeSourceType = 'financial_report' | 'announcement' | 'news' | 'analysis' | 'personal_note' | 'other'
export type RagSource = {
  document_id: string; title: string; filename: string; source_type: KnowledgeSourceType; page_number: number | null;
  chunk_index: number; content: string; score: number
}
export type RagAnswer = { answer: string; sources: RagSource[] }
export type AgentEventName =
  | 'planning'
  | 'tool_started'
  | 'tool_completed'
  | 'awaiting_confirmation'
  | 'background_task_created'
  | 'synthesizing'
export type AgentActivity = {
  id: string
  phase: AgentEventName
  status: string
  tool_call_id?: string
  tool_name?: string
  arguments?: Record<string, unknown>
  result?: Record<string, unknown>
  duration_ms?: number
}
export type ToolExecution = {
  name: string
  arguments?: Record<string, unknown>
  result: Record<string, unknown>
  status?: string
  duration_ms?: number
}

async function request<T>(path: string, init: RequestInit = {}, token = ''): Promise<T> {
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail || '请求失败，请稍后重试。')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export type ChatStreamEvent =
  | { event: AgentEventName; data: AgentActivity }
  | { event: 'token'; data: { content: string } }
  | { event: 'message'; data: ChatMessage }

const AGENT_EVENT_NAMES = new Set<AgentEventName>([
  'planning',
  'tool_started',
  'tool_completed',
  'awaiting_confirmation',
  'background_task_created',
  'synthesizing',
])

async function streamMessage(
  token: string,
  conversationId: string,
  content: string,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<ChatMessage> {
  const response = await fetch(`${API_BASE_URL}/chat/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail || '发送失败，请稍后重试。')
  }
  if (!response.body) throw new Error('浏览器不支持流式响应。')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalMessage: ChatMessage | null = null

  function consume(block: string) {
    const event = block.split('\n').find((line) => line.startsWith('event:'))?.slice(6).trim()
    const dataText = block.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('\n')
    if (!event || !dataText) return
    const data = JSON.parse(dataText) as Record<string, unknown>
    if (event === 'error') throw new Error(String(data.detail || '消息生成失败'))
    if (AGENT_EVENT_NAMES.has(event as AgentEventName)) {
      onEvent({ event: event as AgentEventName, data: data as AgentActivity })
    }
    if (event === 'token') onEvent({ event, data: data as { content: string } })
    if (event === 'message') {
      finalMessage = data as ChatMessage
      onEvent({ event, data: finalMessage })
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      consume(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }
  if (buffer.trim()) consume(buffer)
  if (!finalMessage) throw new Error('流式响应未返回最终消息。')
  return finalMessage
}

export const api = {
  register: (payload: { email: string; username: string; password: string }) =>
    request<AuthResult>('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  login: (payload: { email: string; password: string }) =>
    request<AuthResult>('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  jobs: (token: string) => request<ResearchJob[]>('/research/jobs', {}, token),
  submitResearch: (token: string, payload: { stock_code: string; depth: string; risk_profile: string }) =>
    request<ResearchJob>('/research/jobs', { method: 'POST', body: JSON.stringify(payload) }, token),
  report: (token: string, jobId: string) => request<ResearchReport>(`/research/jobs/${jobId}/report`, {}, token),
  positions: (token: string, refreshMarket = true) => request<Position[]>(`/portfolio/positions?refresh_market=${refreshMarket}`, {}, token),
  savePosition: (token: string, payload: Omit<StoredPosition, 'id'>) =>
    request<StoredPosition>(`/portfolio/positions/${payload.stock_code}`, { method: 'PUT', body: JSON.stringify(payload) }, token),
  conversations: (token: string) => request<Conversation[]>('/chat/conversations', {}, token),
  createConversation: (token: string) => request<Conversation>('/chat/conversations', { method: 'POST' }, token),
  conversation: (token: string, id: string) => request<Conversation>(`/chat/conversations/${id}`, {}, token),
  streamMessage,
  confirmTool: (token: string, conversationId: string, messageId: string) =>
    request<ChatMessage>(`/chat/conversations/${conversationId}/confirm/${messageId}`, { method: 'POST' }, token),
  memories: (token: string) => request<MemoryItem[]>('/memory', {}, token),
  saveMemory: (token: string, payload: { memory_type: string; memory_key: string; memory_value: unknown; confidence?: number }) =>
    request<MemoryItem>('/memory', { method: 'POST', body: JSON.stringify(payload) }, token),
  updateMemory: (token: string, id: string, payload: { memory_value?: unknown; confidence?: number; status?: string }) =>
    request<MemoryItem>(`/memory/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }, token),
  deleteMemory: (token: string, id: string) =>
    request<void>(`/memory/${id}`, { method: 'DELETE' }, token),
  documents: (token: string) => request<KnowledgeDocument[]>('/knowledge/documents', {}, token),
  uploadDocument: (token: string, file: File, title: string, stockCode: string, sourceType: KnowledgeSourceType) => {
    const body = new FormData()
    body.set('file', file)
    if (title.trim()) body.set('title', title.trim())
    if (stockCode.trim()) body.set('stock_code', stockCode.trim())
    body.set('source_type', sourceType)
    return request<KnowledgeDocument>('/knowledge/documents', { method: 'POST', body }, token)
  },
  deleteDocument: (token: string, id: string) =>
    request<void>(`/knowledge/documents/${id}`, { method: 'DELETE' }, token),
  queryKnowledge: (token: string, payload: { question: string; document_ids?: string[]; stock_code?: string; source_types?: KnowledgeSourceType[]; top_k?: number }) =>
    request<RagAnswer>('/knowledge/query', { method: 'POST', body: JSON.stringify(payload) }, token),
}

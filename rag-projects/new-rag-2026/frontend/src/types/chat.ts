// ─── Source chunk from GraphRAG retrieval ────────────────────────────────────
export interface Source {
  type: 'text_unit' | 'community_report' | string
  id?: string
  text?: string
  summary?: string
  title?: string
  document?: string
  document_id?: string
}

// ─── Per-domain agent result (from /agent_trace) ─────────────────────────────
export interface AgentResult {
  domain_key: string
  domain_name_vi: string
  answer: string
  sources_count: number
}

// ─── Chat API request ─────────────────────────────────────────────────────────
export interface ChatRequest {
  session_id: string
  message: string
  mode?: 'auto' | 'local' | 'global'
}

// ─── Chat API response ────────────────────────────────────────────────────────
export interface ChatResponse {
  reply: string
  sources: Source[]
  query_type: string
  session_id: string
  domain_keys: string[]
  agent_count: number
}

// ─── Agent trace response ─────────────────────────────────────────────────────
export interface AgentTraceResponse {
  session_id: string
  last_question: string
  domain_keys: string[]
  search_mode: string
  agent_results: AgentResult[]
}

// ─── Chat message (local state) ───────────────────────────────────────────────
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  sources: Source[]
  domain_keys?: string[]
  query_type?: string
  agent_count?: number
}

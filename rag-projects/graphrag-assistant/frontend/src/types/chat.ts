export interface PolicySource {
  source_file: string
  doc_type: string
  doc_type_label: string
  page_number: number
  excerpt: string
  relevance_score: number
  entities: string
}

export interface GraphNode {
  id: string
  label: string
  type: string
  description: string
}

export interface GraphEdge {
  source: string
  relation: string
  target: string
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  sources: PolicySource[]
  query_type?: 'LOCAL' | 'GLOBAL'
  graph_data?: GraphData
}

export interface ChatRequest {
  session_id: string
  message: string
}

export interface ChatResponse {
  session_id: string
  reply: string
  sources: PolicySource[]
  query_type: 'LOCAL' | 'GLOBAL'
  graph_data?: GraphData
  is_fallback?: boolean
}

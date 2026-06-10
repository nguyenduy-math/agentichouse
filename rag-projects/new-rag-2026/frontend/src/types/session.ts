export interface Session {
  session_id: string
}

export interface HealthResponse {
  status: string
  neo4j_connected: boolean
  graphrag_ready: boolean
}

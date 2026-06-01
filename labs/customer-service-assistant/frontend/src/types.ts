export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  agentUsed?: string
}

export interface ActivityItem {
  agent: string
  action: string
  detail?: string
}

export interface ChatResponse {
  reply: string
  agent_used: string
  activities: ActivityItem[]
}

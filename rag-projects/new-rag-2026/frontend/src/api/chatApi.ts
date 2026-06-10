import client from './client'
import type { ChatRequest, ChatResponse, AgentTraceResponse } from '../types/chat'

export const sendMessage = async (request: ChatRequest): Promise<ChatResponse> => {
  const { data } = await client.post<ChatResponse>('/chat', request)
  return data
}

export const getAgentTrace = async (sessionId: string): Promise<AgentTraceResponse> => {
  const { data } = await client.get<AgentTraceResponse>(`/chat/${sessionId}/agent_trace`)
  return data
}

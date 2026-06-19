import client from './client'
import type { ChatRequest, ChatResponse } from '../types/chat'

export const sendMessage = async (request: ChatRequest): Promise<ChatResponse> => {
  const { data } = await client.post<ChatResponse>('/chat', request)
  return data
}

export const getChatHistory = async (sessionId: string) => {
  const { data } = await client.get(`/chat/${sessionId}/history`)
  return data
}

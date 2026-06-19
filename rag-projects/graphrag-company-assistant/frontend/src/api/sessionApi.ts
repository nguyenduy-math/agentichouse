import client from './client'
import type { Session } from '../types/session'

export const createSession = async (): Promise<Session> => {
  const { data } = await client.post<Session>('/session')
  return data
}

export const deleteSession = async (sessionId: string): Promise<void> => {
  await client.delete(`/session/${sessionId}`)
}

import client from './client'
import type { AdminTokenRow, SessionTokenSummary } from '../types/token'

export const getSessionTokens = (sessionId: string) =>
  client.get<SessionTokenSummary>(`/sessions/${sessionId}/tokens`)

export const getAdminTokenSummary = (limit = 100) =>
  client.get<AdminTokenRow[]>('/admin/tokens/summary', { params: { limit } })

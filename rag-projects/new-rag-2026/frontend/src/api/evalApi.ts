import client from './client'
import type {
  EvalRunListResponse,
  EvalRunRequest,
  EvalRunResult,
  EvalRunStartResponse,
  SessionListResponse,
  SessionTurnsResponse,
} from '../types/eval'

export const listSessions = (limit = 50, offset = 0) =>
  client.get<SessionListResponse>('/eval/sessions', { params: { limit, offset } })

export const getSessionTurns = (sessionId: string) =>
  client.get<SessionTurnsResponse>(`/eval/sessions/${sessionId}/turns`)

export const startEvalRun = (body: EvalRunRequest) =>
  client.post<EvalRunStartResponse>('/eval/run', body)

export const listRuns = (limit = 20) =>
  client.get<EvalRunListResponse>('/eval/runs', { params: { limit } })

export const getRunResult = (runId: string) =>
  client.get<EvalRunResult>(`/eval/runs/${runId}`)

export const exportRun = (runId: string) =>
  client.get<Blob>(`/eval/runs/${runId}/export`, { responseType: 'blob' })

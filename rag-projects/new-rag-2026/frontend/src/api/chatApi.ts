import client from './client'
import type { ChatRequest, ChatResponse, AgentTraceResponse, ProgressEvent } from '../types/chat'

export const sendMessage = async (request: ChatRequest): Promise<ChatResponse> => {
  const { data } = await client.post<ChatResponse>('/chat', request)
  return data
}

export const getAgentTrace = async (sessionId: string): Promise<AgentTraceResponse> => {
  const { data } = await client.get<AgentTraceResponse>(`/chat/${sessionId}/agent_trace`)
  return data
}

/**
 * Open an SSE connection to the pipeline progress stream for a session.
 *
 * Call this BEFORE (or simultaneously with) sendMessage() so the EventSource
 * is established when the backend starts emitting events.
 * Returns a cleanup function — call it to close the connection.
 */
export function openProgressStream(
  sessionId: string,
  onEvent: (event: ProgressEvent) => void,
  onDone: () => void,
): () => void {
  const es = new EventSource(`/api/v1/chat/${sessionId}/progress`)

  es.onmessage = (e: MessageEvent) => {
    try {
      const ev = JSON.parse(e.data as string) as ProgressEvent
      onEvent(ev)
      if (ev.type === 'done' || ev.type === 'error') {
        es.close()
        onDone()
      }
    } catch {
      // ignore malformed frames
    }
  }

  es.onerror = () => {
    es.close()
    onDone()
  }

  return () => es.close()
}

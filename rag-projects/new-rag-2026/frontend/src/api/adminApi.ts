import client from './client'

export interface IngestResponse {
  filename: string
  status: string
}

export interface IndexResponse {
  status: string
}

export interface IndexStatus {
  status: string
  message: string | null
  last_completed_at: string | null
}

export const ingestDocument = async (file: File, domain: string): Promise<IngestResponse> => {
  const form = new FormData()
  form.append('file', file)
  form.append('domain', domain)
  const { data } = await client.post<IngestResponse>('/admin/ingest', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export const triggerIndex = async (reimport = false, domain = 'general'): Promise<IndexResponse> => {
  const { data } = await client.post<IndexResponse>('/admin/index', { reimport, domain })
  return data
}

export const getIndexStatus = async (): Promise<IndexStatus> => {
  const { data } = await client.get<IndexStatus>('/admin/status')
  return data
}

/**
 * Open an SSE connection to the indexing log stream.
 *
 * Sends buffered lines from `offset` immediately, then streams new lines
 * as the pipeline runs. Calls `onDone` with the terminal status string
 * ('ready' | 'error' | 'idle') when the pipeline finishes or on error.
 *
 * Returns a cleanup function — call it to close the connection early.
 */
export function openIndexLogStream(
  offset: number,
  onLine: (line: string) => void,
  onProgress: (pct: number) => void,
  onDone: (status: string) => void,
): () => void {
  const es = new EventSource(`/api/v1/admin/logs?offset=${offset}`)

  es.onmessage = (e: MessageEvent) => {
    onLine(e.data as string)
  }

  es.addEventListener('progress', (e) => {
    const pct = parseInt((e as MessageEvent).data as string, 10)
    if (!isNaN(pct)) onProgress(pct)
  })

  es.addEventListener('done', (e) => {
    onDone((e as MessageEvent).data as string)
    es.close()
  })

  es.onerror = () => {
    es.close()
    onDone('error')
  }

  return () => es.close()
}

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

export const ingestDocument = async (file: File): Promise<IngestResponse> => {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post<IngestResponse>('/admin/ingest', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export const triggerIndex = async (reimport = false): Promise<IndexResponse> => {
  const { data } = await client.post<IndexResponse>('/admin/index', { reimport })
  return data
}

export const getIndexStatus = async (): Promise<IndexStatus> => {
  const { data } = await client.get<IndexStatus>('/admin/status')
  return data
}

import client from './client'

export interface IngestResponse {
  filename: string
  status: string
}

export interface IndexResponse {
  status: string
}

export interface IndexStatus {
  stage: string
  done: number
  total: number
  status: string
  last_error: string | null
}

export const ingestDocument = async (file: File): Promise<IngestResponse> => {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post<IngestResponse>('/admin/ingest', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export const triggerIndex = async (): Promise<IndexResponse> => {
  const { data } = await client.post<IndexResponse>('/admin/index')
  return data
}

export const getIndexStatus = async (): Promise<IndexStatus> => {
  const { data } = await client.get<IndexStatus>('/admin/status')
  return data
}

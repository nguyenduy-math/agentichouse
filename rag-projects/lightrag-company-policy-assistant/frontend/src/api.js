// Thin fetch wrapper for the FastAPI backend.
// All calls go through /api, which Vite proxies to the backend in dev.

const API_BASE = '/api'

async function postJSON(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`HTTP ${response.status}: ${detail}`)
  }
  return response.json()
}

// Multi-turn chat. Returns { answer, domains_consulted, citations, entities, history }.
export function sendChat(message, history) {
  return postJSON('/chat', { message, history })
}

// Ingest the server-side document folder.
export function ingestFolder(folder = null) {
  return postJSON('/ingest', { folder })
}

// Upload + ingest files via multipart. doc_type must match a valid domain folder.
export async function uploadFiles(fileList, docType) {
  const form = new FormData()
  for (const file of fileList) form.append('files', file)
  form.append('doc_type', docType)
  const response = await fetch(`${API_BASE}/ingest/upload`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`HTTP ${response.status}: ${detail}`)
  }
  return response.json()
}

export async function getHealth() {
  const response = await fetch(`${API_BASE}/health`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

export async function getAdminStats() {
  const response = await fetch(`${API_BASE}/admin/stats`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

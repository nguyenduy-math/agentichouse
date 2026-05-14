// Thin fetch wrapper for the FastAPI backend.
// All calls go through /api, which Vite proxies to the backend in dev and
// FastAPI serves directly in production (same origin).

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

// Multi-turn chat. `history` is [{ role, content }, ...] from previous turns.
export function sendChat(message, history, mode) {
  return postJSON('/chat', { message, history, mode })
}

// One-shot query without conversation history.
export function runQuery(question, mode) {
  return postJSON('/query', { question, mode })
}

// Ingest the server-side document folder (pass null for the configured default).
export function ingestFolder(folder = null) {
  return postJSON('/ingest', { folder })
}

// Upload + ingest files via multipart.
export async function uploadFiles(fileList) {
  const form = new FormData()
  for (const file of fileList) form.append('files', file)
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

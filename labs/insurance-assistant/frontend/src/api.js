const BASE = '/api'

export async function newSession(mode) {
  const res = await fetch(`${BASE}/session/new`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  })
  if (!res.ok) throw new Error('Failed to create session')
  return res.json()
}

export async function sendMessage(sessionId, message) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })
  if (!res.ok) throw new Error('Chat request failed')
  return res.json()
}

export async function uploadPdf(sessionId, file) {
  const formData = new FormData()
  formData.append('session_id', sessionId)
  formData.append('file', file)
  const res = await fetch(`${BASE}/upload-pdf`, { method: 'POST', body: formData })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'PDF upload failed')
  }
  return res.json()
}

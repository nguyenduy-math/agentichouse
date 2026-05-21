// Lớp gọi API mỏng tới backend FastAPI.
// Mọi request đi qua /api và được Vite proxy (strip /api) sang backend khi chạy dev.

const API_BASE = '/api'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`HTTP ${response.status}: ${detail}`)
  }
  return response.json()
}

function postJSON(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// Hỏi đáp đa lượt. Trả về { answer, citations, documents_consulted }.
export function sendChat(message, history) {
  return postJSON('/chat', { message, history })
}

// Tải lên một tệp PDF. Trả về { doc_id, filename, status, tree_path, node_count }.
export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/ingest/upload', { method: 'POST', body: form })
}

// Danh sách tài liệu đã nạp: [{ doc_id, filename, node_count }].
export function listDocs() {
  return request('/ingest/list')
}

// Xoá một tài liệu theo doc_id.
export function deleteDoc(docId) {
  return request(`/ingest/${encodeURIComponent(docId)}`, { method: 'DELETE' })
}

// Trạng thái máy chủ: { status, indexed_count, pageindex_key_present, gemini_key_present }.
export function getHealth() {
  return request('/health')
}

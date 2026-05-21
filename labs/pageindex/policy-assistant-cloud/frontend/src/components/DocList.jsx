import { useEffect, useState } from 'react'
import { listDocs, deleteDoc } from '../api.js'

// Danh sách tài liệu đã nạp + nút xoá. Tự nạp lại khi refreshKey đổi.
export default function DocList({ refreshKey, onDocsChanged }) {
  const [docs, setDocs] = useState([])
  const [busy, setBusy] = useState(null) // doc_id đang xoá

  useEffect(() => {
    listDocs()
      .then(setDocs)
      .catch(() => setDocs([]))
  }, [refreshKey])

  async function handleDelete(docId) {
    setBusy(docId)
    try {
      await deleteDoc(docId)
      onDocsChanged?.()
    } catch {
      // bỏ qua — danh sách sẽ được làm mới ở lần sau
    } finally {
      setBusy(null)
    }
  }

  if (docs.length === 0) {
    return <div className="doclist doclist--empty">Chưa có tài liệu nào.</div>
  }

  return (
    <div className="doclist">
      {docs.map((d) => (
        <span key={d.doc_id} className="doclist__item" title={d.doc_id}>
          <span className="doclist__name">{d.filename}</span>
          <span className="doclist__count">· {d.node_count} node</span>
          <button
            className="doclist__del"
            onClick={() => handleDelete(d.doc_id)}
            disabled={busy === d.doc_id}
            title="Xoá tài liệu"
          >
            {busy === d.doc_id ? '…' : '×'}
          </button>
        </span>
      ))}
    </div>
  )
}

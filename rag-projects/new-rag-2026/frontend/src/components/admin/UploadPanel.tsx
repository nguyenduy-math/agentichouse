import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileCheck, AlertCircle, Play } from 'lucide-react'
import { ingestDocument, triggerIndex } from '../../api/adminApi'
import IndexStatus from './IndexStatus'

interface UploadedFile {
  name: string
  status: 'uploading' | 'done' | 'error'
  message?: string
}

export default function UploadPanel() {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [indexing, setIndexing] = useState(false)
  const [polling, setPolling] = useState(false)
  const [indexError, setIndexError] = useState<string | null>(null)

  const onDrop = useCallback(async (accepted: File[]) => {
    for (const file of accepted) {
      setFiles((prev) => [...prev, { name: file.name, status: 'uploading' }])
      try {
        await ingestDocument(file)
        setFiles((prev) =>
          prev.map((f) =>
            f.name === file.name ? { ...f, status: 'done' } : f
          )
        )
      } catch {
        setFiles((prev) =>
          prev.map((f) =>
            f.name === file.name
              ? { ...f, status: 'error', message: 'Tải lên thất bại' }
              : f
          )
        )
      }
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
    },
    multiple: true,
  })

  const handleTriggerIndex = async () => {
    setIndexing(true)
    setIndexError(null)
    setPolling(true)
    try {
      await triggerIndex()
    } catch {
      setIndexError('Không thể bắt đầu lập chỉ mục. Kiểm tra kết nối backend.')
      setPolling(false)
    } finally {
      setIndexing(false)
    }
  }

  const hasDoneFiles = files.some((f) => f.status === 'done')

  return (
    <div className="max-w-2xl mx-auto py-6 px-4 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-200">Tải tài liệu</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Chấp nhận PDF, DOCX, TXT. Kéo thả hoặc nhấn để chọn.
        </p>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          isDragActive
            ? 'border-blue-500 bg-blue-900/10'
            : 'border-slate-600 hover:border-slate-500 hover:bg-slate-800/50'
        }`}
      >
        <input {...getInputProps()} />
        <Upload className="w-10 h-10 text-slate-500 mx-auto mb-3" />
        {isDragActive ? (
          <p className="text-blue-400 text-sm font-medium">Thả tài liệu vào đây...</p>
        ) : (
          <>
            <p className="text-slate-300 text-sm font-medium">
              Kéo thả tài liệu hoặc nhấn để chọn
            </p>
            <p className="text-slate-600 text-xs mt-1">PDF · DOCX · TXT</p>
          </>
        )}
      </div>

      {/* Uploaded file list */}
      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((f, i) => (
            <div
              key={i}
              className="flex items-center gap-3 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"
            >
              {f.status === 'done' ? (
                <FileCheck className="w-4 h-4 text-green-400 flex-shrink-0" />
              ) : f.status === 'error' ? (
                <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
              ) : (
                <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
              )}
              <span className="flex-1 text-slate-300 truncate">{f.name}</span>
              <span
                className={`text-xs ${
                  f.status === 'done'
                    ? 'text-green-400'
                    : f.status === 'error'
                    ? 'text-red-400'
                    : 'text-blue-400'
                }`}
              >
                {f.status === 'done'
                  ? 'Đã tải'
                  : f.status === 'error'
                  ? f.message ?? 'Lỗi'
                  : 'Đang tải...'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Index button */}
      <div>
        <button
          onClick={handleTriggerIndex}
          disabled={indexing || !hasDoneFiles}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Play className="w-4 h-4" />
          Bắt đầu lập chỉ mục
        </button>
        {!hasDoneFiles && (
          <p className="text-xs text-slate-600 mt-1">
            Tải ít nhất một tài liệu để bắt đầu lập chỉ mục.
          </p>
        )}
        {indexError && (
          <p className="text-xs text-red-400 mt-1">{indexError}</p>
        )}
      </div>

      {/* Index status */}
      <IndexStatus polling={polling} />
    </div>
  )
}

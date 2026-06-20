import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileCheck, AlertCircle, Play } from 'lucide-react'
import { ingestDocument } from '../../api/adminApi'
import { useIndexLogs } from '../../hooks/useIndexLogs'
import IndexStatus from './IndexStatus'
import { DOMAIN_CONFIG } from '../agent/DomainBadge'

const DOMAIN_OPTIONS = Object.entries(DOMAIN_CONFIG).map(([key, cfg]) => ({
  key,
  label: cfg.label,
}))

interface UploadedFile {
  name: string
  status: 'uploading' | 'done' | 'error'
  domain: string
  message?: string
}

export default function UploadPanel() {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [selectedDomain, setSelectedDomain] = useState<string>('hr')
  const [indexError, setIndexError] = useState<string | null>(null)
  const { lines, status, isStreaming, pct, startIndexing } = useIndexLogs()

  const onDrop = useCallback(
    async (accepted: File[]) => {
      setUploading(true)
      for (const file of accepted) {
        setFiles((prev) => [
          ...prev,
          { name: file.name, status: 'uploading', domain: selectedDomain },
        ])
        try {
          await ingestDocument(file, selectedDomain)
          setFiles((prev) =>
            prev.map((f) =>
              f.name === file.name && f.domain === selectedDomain
                ? { ...f, status: 'done' }
                : f,
            ),
          )
        } catch {
          setFiles((prev) =>
            prev.map((f) =>
              f.name === file.name && f.domain === selectedDomain
                ? { ...f, status: 'error', message: 'Tải lên thất bại' }
                : f,
            ),
          )
        }
      }
      setUploading(false)
    },
    [selectedDomain],
  )

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
    setIndexError(null)
    try {
      // Index only the domain that has new files
      const domainToIndex = files.find((f) => f.status === 'done')?.domain ?? selectedDomain
      await startIndexing(false, domainToIndex)
    } catch {
      setIndexError('Không thể bắt đầu lập chỉ mục. Kiểm tra kết nối backend.')
    }
  }

  const hasDoneFiles = files.some((f) => f.status === 'done')
  const isRunning = isStreaming || status === 'indexing' || status === 'importing'
  const showStatus = status !== 'idle' || lines.length > 0

  // Group uploaded files by domain for display
  const filesByDomain = files.reduce<Record<string, UploadedFile[]>>((acc, f) => {
    ;(acc[f.domain] ??= []).push(f)
    return acc
  }, {})

  return (
    <div className="max-w-2xl mx-auto py-6 px-4 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-200">Tải tài liệu</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Chọn lĩnh vực, rồi kéo thả hoặc nhấn để chọn tài liệu (PDF, DOCX, TXT).
        </p>
      </div>

      {/* Domain selector */}
      <div>
        <label className="block text-xs font-medium text-slate-400 mb-1.5">
          Lĩnh vực tài liệu
        </label>
        <div className="flex flex-wrap gap-2">
          {DOMAIN_OPTIONS.map(({ key, label }) => {
            const cfg = DOMAIN_CONFIG[key]
            const isSelected = selectedDomain === key
            const colorClass = cfg.classes
              .split(' ')
              .find((c) => c.startsWith('border-')) ?? 'border-slate-600'
            return (
              <button
                key={key}
                onClick={() => setSelectedDomain(key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  isSelected
                    ? `${colorClass} bg-slate-700 text-slate-100 ring-1 ring-offset-1 ring-offset-slate-900 ${colorClass}`
                    : 'border-slate-700 bg-slate-800 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                }`}
              >
                {label}
              </button>
            )
          })}
        </div>
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
            <p className="text-slate-500 text-xs mt-1">
              Sẽ được thêm vào lĩnh vực:{' '}
              <span className="text-slate-300 font-medium">
                {DOMAIN_CONFIG[selectedDomain]?.label}
              </span>
            </p>
            <p className="text-slate-600 text-xs mt-0.5">PDF · DOCX · TXT</p>
          </>
        )}
      </div>

      {/* Uploaded file list grouped by domain */}
      {Object.entries(filesByDomain).length > 0 && (
        <div className="space-y-3">
          {Object.entries(filesByDomain).map(([domainKey, domainFiles]) => (
            <div key={domainKey}>
              <p className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                {DOMAIN_CONFIG[domainKey]?.label ?? domainKey}
              </p>
              <div className="space-y-1.5">
                {domainFiles.map((f, i) => (
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
                        ? (f.message ?? 'Lỗi')
                        : 'Đang tải...'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Index button */}
      <div>
        <button
          onClick={handleTriggerIndex}
          disabled={uploading || isRunning || !hasDoneFiles}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Play className="w-4 h-4" />
          {isRunning ? 'Đang lập chỉ mục...' : 'Bắt đầu lập chỉ mục'}
        </button>
        {!hasDoneFiles && !isRunning && (
          <p className="text-xs text-slate-600 mt-1">
            Tải ít nhất một tài liệu để bắt đầu lập chỉ mục.
          </p>
        )}
        {indexError && (
          <p className="text-xs text-red-400 mt-1">{indexError}</p>
        )}
      </div>

      {/* Live index status + log console */}
      {showStatus && (
        <IndexStatus status={status} isStreaming={isStreaming} pct={pct} lines={lines} />
      )}
    </div>
  )
}

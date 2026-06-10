import { useState } from 'react'
import { startEvalRun } from '../../api/evalApi'
import type { EvalTurn } from '../../types/eval'

const PROVIDERS = ['openai', 'gemini', 'siliconflow'] as const
type Provider = (typeof PROVIDERS)[number]

const DEFAULT_MODELS: Record<Provider, string> = {
  openai: 'gpt-4o-mini',
  gemini: 'gemini-2.0-flash',
  siliconflow: 'deepseek-ai/DeepSeek-V3',
}

interface Props {
  selectedTurns: EvalTurn[]
  onClose: () => void
  onStarted: (runId: string) => void
}

export default function EvalConfigModal({ selectedTurns, onClose, onStarted }: Props) {
  const [provider, setProvider] = useState<Provider>('openai')
  const [model, setModel] = useState(DEFAULT_MODELS['openai'])
  const [referenceAnswers, setReferenceAnswers] = useState<Record<string, string>>({})
  const [showRef, setShowRef] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleProviderChange = (p: Provider) => {
    setProvider(p)
    setModel(DEFAULT_MODELS[p])
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const res = await startEvalRun({
        turn_ids: selectedTurns.map((t) => t.turn_id),
        judge_provider: provider,
        judge_model: model,
        reference_answers: referenceAnswers,
      })
      onStarted(res.data.run_id)
      onClose()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Lỗi không xác định'
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div className="px-5 py-4 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-slate-100">Cấu hình đánh giá</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {selectedTurns.length} lượt được chọn
          </p>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* Provider selector */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-2">
              LLM chấm điểm
            </label>
            <div className="flex gap-2">
              {PROVIDERS.map((p) => (
                <button
                  key={p}
                  onClick={() => handleProviderChange(p)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
                    provider === p
                      ? 'bg-blue-700 border-blue-600 text-white'
                      : 'bg-slate-800 border-slate-700 text-slate-300 hover:border-slate-500'
                  }`}
                >
                  {p === 'openai' ? 'OpenAI' : p === 'gemini' ? 'Gemini' : 'Siliconflow'}
                </button>
              ))}
            </div>
          </div>

          {/* Model input */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Model
            </label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-slate-800 border border-slate-700 rounded-md text-slate-200 focus:outline-none focus:border-blue-600"
            />
          </div>

          {/* Reference answers (collapsible) */}
          <div>
            <button
              onClick={() => setShowRef(!showRef)}
              className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1.5 transition-colors"
            >
              <span>{showRef ? '▼' : '▶'}</span>
              Câu trả lời tham chiếu (tuỳ chọn)
            </button>
            {showRef && (
              <div className="mt-3 space-y-3">
                <p className="text-xs text-slate-500 italic">
                  Bỏ qua nếu không có câu trả lời tham chiếu — context_recall và
                  answer_correctness sẽ bị bỏ qua.
                </p>
                {selectedTurns.map((t) => (
                  <div key={t.turn_id}>
                    <p className="text-xs text-slate-400 mb-1 truncate">
                      #{t.turn_number}: {t.question.slice(0, 60)}…
                    </p>
                    <textarea
                      value={referenceAnswers[t.turn_id] ?? ''}
                      onChange={(e) =>
                        setReferenceAnswers((prev) => ({
                          ...prev,
                          [t.turn_id]: e.target.value,
                        }))
                      }
                      rows={2}
                      placeholder="Câu trả lời chuẩn (để trống nếu không có)"
                      className="w-full px-2 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-md text-slate-200 focus:outline-none focus:border-blue-600 resize-none"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-900/20 px-3 py-2 rounded-md">{error}</p>
          )}
        </div>

        <div className="px-5 py-4 border-t border-slate-700 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            Huỷ
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Đang gửi...' : 'Bắt đầu đánh giá'}
          </button>
        </div>
      </div>
    </div>
  )
}

// TypeScript types matching the eval API response shapes

export interface EvalTurn {
  turn_id: string
  session_id: string
  turn_number: number
  question: string
  answer: string
  sources: Record<string, unknown>[]
  domain_keys: string[]
  query_type: string
  is_fallback: boolean
  timestamp: string
}

export interface SessionSummary {
  session_id: string
  turn_count: number
  last_active: string
  created_at: string
}

export interface SessionListResponse {
  sessions: SessionSummary[]
  total: number
}

export interface SessionTurnsResponse {
  session_id: string
  turns: EvalTurn[]
}

export interface EvalRunRequest {
  turn_ids: string[]
  judge_provider: string
  judge_model: string
  reference_answers: Record<string, string>
}

export interface EvalRunStartResponse {
  run_id: string
  status: string
  turn_count: number
}

export interface EvalTurnScore {
  turn_id: string
  question: string
  answer: string
  domain_keys: string[]
  query_type: string
  faithfulness: number | null
  answer_relevancy: number | null
  context_precision: number | null
  context_recall: number | null
  answer_correctness: number | null
  reference_answer: string
}

export interface EvalRunResult {
  run_id: string
  status: string
  judge_provider: string
  judge_model: string
  created_at: string
  turn_count: number
  error: string | null
  scores: EvalTurnScore[]
  averages: Record<string, number | null>
}

export interface EvalRunSummary {
  run_id: string
  created_at: string
  turn_count: number
  judge_provider: string
  judge_model: string
  status: 'pending' | 'running' | 'done' | 'failed'
  error: string | null
}

export interface EvalRunListResponse {
  runs: EvalRunSummary[]
}

export const METRIC_NAMES = [
  'faithfulness',
  'answer_relevancy',
  'context_precision',
  'context_recall',
  'answer_correctness',
] as const

export type MetricName = (typeof METRIC_NAMES)[number]

export const METRIC_LABELS: Record<MetricName, string> = {
  faithfulness: 'Độ trung thực',
  answer_relevancy: 'Liên quan câu trả lời',
  context_precision: 'Độ chính xác ngữ cảnh',
  context_recall: 'Độ bao phủ ngữ cảnh',
  answer_correctness: 'Độ chính xác câu trả lời',
}

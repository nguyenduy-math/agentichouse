export interface CallTypeBreakdown {
  call_type: string
  total_tokens: number
  cost_usd: number
  calls: number
}

export interface ModelBreakdown {
  provider: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost_usd: number
}

export interface TurnBreakdown {
  turn_id: string
  turn_number: number | null
  total_tokens: number
  cost_usd: number
  calls: number
}

export interface SessionTokenSummary {
  session_id: string
  total_prompt_tokens: number
  total_completion_tokens: number
  total_tokens: number
  total_cost_usd: number
  total_calls: number
  by_call_type: CallTypeBreakdown[]
  by_model: ModelBreakdown[]
  turn_breakdown: TurnBreakdown[]
}

export interface AdminTokenRow {
  session_id: string
  total_tokens: number
  total_cost_usd: number
  total_calls: number
  first_call: string
  last_call: string
}

import { useChatStore } from '../../store'
import { DOMAIN_CONFIG } from '../agent/DomainBadge'
import type { ProgressEvent } from '../../types/chat'

// ── Helpers ───────────────────────────────────────────────────────────────────

type StepKey = 'rewrite' | 'retrieve' | 'synthesize' | 'verify'

const STEP_LABEL: Record<StepKey, string> = {
  rewrite:    'Cải thiện câu hỏi',
  retrieve:   'Truy xuất tri thức',
  synthesize: 'Tổng hợp câu trả lời',
  verify:     'Xác minh kết quả',
}

type AgentState = 'waiting' | 'running' | 'done'

interface DerivedState {
  activeSteps: Set<StepKey>
  doneSteps: Set<StepKey>
  domains: string[]
  agentStates: Record<string, AgentState>
  mode: string | null
  finished: boolean
}

function deriveState(events: ProgressEvent[]): DerivedState {
  const activeSteps = new Set<StepKey>()
  const doneSteps = new Set<StepKey>()
  const domains: string[] = []
  const agentStates: Record<string, AgentState> = {}
  let mode: string | null = null
  let finished = false

  for (const ev of events) {
    if (ev.type === 'step') {
      // A step that was active is now superseded by the next one → mark done
      activeSteps.forEach((s) => {
        if (s !== ev.step) doneSteps.add(s)
      })
      activeSteps.clear()
      if (!doneSteps.has(ev.step)) activeSteps.add(ev.step)
    } else if (ev.type === 'classified') {
      // rewrite step completes when classification arrives
      doneSteps.add('rewrite')
      activeSteps.delete('rewrite')
      ev.domains.forEach((d) => {
        if (!domains.includes(d)) {
          domains.push(d)
          agentStates[d] = 'waiting'
        }
      })
      mode = ev.mode
    } else if (ev.type === 'agent_start') {
      agentStates[ev.domain] = 'running'
    } else if (ev.type === 'agent_done') {
      agentStates[ev.domain] = 'done'
    } else if (ev.type === 'done' || ev.type === 'error') {
      activeSteps.forEach((s) => doneSteps.add(s))
      activeSteps.clear()
      finished = true
    }
  }

  return { activeSteps, doneSteps, domains, agentStates, mode, finished }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <span className="inline-block w-3.5 h-3.5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
  )
}

function StepRow({ label, state }: { label: string; state: 'waiting' | 'active' | 'done' }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {state === 'done' ? (
        <span className="text-green-400 flex-shrink-0">✓</span>
      ) : state === 'active' ? (
        <Spinner />
      ) : (
        <span className="text-slate-600 flex-shrink-0">○</span>
      )}
      <span
        className={
          state === 'done'
            ? 'text-slate-400 line-through'
            : state === 'active'
            ? 'text-slate-200'
            : 'text-slate-600'
        }
      >
        {label}
      </span>
    </div>
  )
}

function AgentRow({ domain, state }: { domain: string; state: AgentState }) {
  const cfg = DOMAIN_CONFIG[domain]
  const label = cfg?.label ?? domain

  // Extract the text colour class for the badge (e.g. "text-blue-300")
  const textCls = cfg?.classes.split(' ').find((c) => c.startsWith('text-')) ?? 'text-slate-300'
  const borderCls = cfg?.classes.split(' ').find((c) => c.startsWith('border-')) ?? 'border-slate-600'

  return (
    <div className={`flex items-center gap-2 text-xs border-l-2 ${borderCls} pl-2`}>
      {state === 'done' ? (
        <span className="text-green-400 flex-shrink-0">✓</span>
      ) : state === 'running' ? (
        <Spinner />
      ) : (
        <span className="text-slate-600 flex-shrink-0">○</span>
      )}
      <span className={state === 'waiting' ? 'text-slate-600' : textCls}>{label}</span>
      {state === 'running' && (
        <span className="text-slate-500 ml-auto">đang trả lời...</span>
      )}
      {state === 'done' && (
        <span className="text-slate-500 ml-auto">xong</span>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AgentProgressPanel() {
  const progressEvents = useChatStore((s) => s.progressEvents)
  const isLoading = useChatStore((s) => s.isLoading)

  if (!isLoading && progressEvents.length === 0) return null

  const { activeSteps, doneSteps, domains, agentStates, mode, finished } =
    deriveState(progressEvents)

  const stepsToShow: StepKey[] = ['rewrite', 'retrieve']
  if (domains.length > 1) stepsToShow.push('synthesize')
  stepsToShow.push('verify')

  return (
    <div className="mx-2 mb-2 p-3 bg-slate-800/60 border border-slate-700/60 rounded-xl space-y-2 text-xs">
      {/* Header */}
      <div className="flex items-center gap-2 text-slate-400">
        <span className="font-medium text-slate-300">Đang xử lý</span>
        {mode && (
          <span className="text-slate-500">
            — {mode === 'global' ? 'tìm kiếm toàn cục' : 'tìm kiếm cục bộ'}
          </span>
        )}
      </div>

      {/* Pipeline steps */}
      <div className="space-y-1.5">
        {stepsToShow.map((step) => (
          <StepRow
            key={step}
            label={STEP_LABEL[step]}
            state={
              doneSteps.has(step) ? 'done' : activeSteps.has(step) ? 'active' : 'waiting'
            }
          />
        ))}
      </div>

      {/* Domain agents (appear after classification) */}
      {domains.length > 0 && (
        <div className="border-t border-slate-700/50 pt-2 space-y-1.5">
          <span className="text-slate-500 text-[10px] uppercase tracking-wide">
            Chuyên gia tham gia ({domains.length})
          </span>
          {domains.map((d) => (
            <AgentRow key={d} domain={d} state={agentStates[d] ?? 'waiting'} />
          ))}
        </div>
      )}

      {finished && (
        <div className="text-green-400 text-[10px] pt-0.5">✓ Hoàn tất</div>
      )}
    </div>
  )
}

import { useState } from 'react'
import SessionList from './SessionList'
import TurnTable from './TurnTable'
import RunList from './RunList'
import EvalResultTable from './EvalResultTable'
import EvalConfigModal from './EvalConfigModal'
import TokenSummaryPanel from './TokenSummaryPanel'
import { useEvalStore } from '../../store/evalStore'
import { getSessionTurns } from '../../api/evalApi'
import type { EvalTurn } from '../../types/eval'

export default function EvalTab() {
  const [modalOpen, setModalOpen] = useState(false)
  const [modalTurns, setModalTurns] = useState<EvalTurn[]>([])

  const selectedSessionId = useEvalStore((s) => s.selectedSessionId)
  const selectedTurnIds = useEvalStore((s) => s.selectedTurnIds)
  const setSelectedRunId = useEvalStore((s) => s.setSelectedRunId)

  const handleRunEval = async () => {
    if (!selectedSessionId || selectedTurnIds.size === 0) return
    // Fetch the full turn objects for the selected ids
    try {
      const res = await getSessionTurns(selectedSessionId)
      const turns = res.data.turns.filter((t) => selectedTurnIds.has(t.turn_id))
      setModalTurns(turns)
      setModalOpen(true)
    } catch {
      // ignore
    }
  }

  const handleStarted = (runId: string) => {
    setSelectedRunId(runId)
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Left column: session browser */}
      <div className="w-72 shrink-0 flex flex-col gap-4 border-r border-slate-700 p-4 overflow-y-auto">
        <SessionList />
        <TurnTable onRunEval={handleRunEval} />
      </div>

      {/* Right column: results panel */}
      <div className="flex-1 flex flex-col gap-4 p-4 overflow-y-auto">
        <RunList />
        {selectedSessionId && (
          <div className="border-t border-slate-700 pt-4">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
              Token — {selectedSessionId.slice(0, 12)}…
            </div>
            <TokenSummaryPanel sessionId={selectedSessionId} />
          </div>
        )}
        <div className="border-t border-slate-700 pt-4">
          <EvalResultTable />
        </div>
      </div>

      {modalOpen && (
        <EvalConfigModal
          selectedTurns={modalTurns}
          onClose={() => setModalOpen(false)}
          onStarted={handleStarted}
        />
      )}
    </div>
  )
}

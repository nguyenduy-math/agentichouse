import Header from './Header'
import ChatWindow from '../chat/ChatWindow'
import ChatInput from '../chat/ChatInput'
import SourcesPanel from '../sources/SourcesPanel'
import AgentTracePanel from '../agent/AgentTracePanel'
import UploadPanel from '../admin/UploadPanel'
import EvalTab from '../eval/EvalTab'
import TokenReportPage from '../tokens/TokenReportPage'
import { useTabStore, useChatStore } from '../../store'

export default function AppShell() {
  const activeTab = useTabStore((s) => s.activeTab)
  const traceOpen = useChatStore((s) => s.traceOpen)
  const activeSources = useChatStore((s) => s.activeSources)

  return (
    <div className="h-full flex flex-col bg-slate-900">
      <Header />

      {activeTab === 'chat' ? (
        /* ── Chat tab: main chat + optional side panels ── */
        <div className="flex flex-1 overflow-hidden">
          {/* Main chat column */}
          <div className="flex flex-col flex-1 min-w-0">
            <ChatWindow />
            <ChatInput />
          </div>

          {/* Sources panel (right sidebar) */}
          {activeSources.length > 0 && <SourcesPanel />}

          {/* Agent trace panel (right sidebar, stacked after sources) */}
          {traceOpen && <AgentTracePanel />}
        </div>
      ) : activeTab === 'admin' ? (
        /* ── Admin tab ── */
        <div className="flex-1 overflow-y-auto bg-slate-900">
          <UploadPanel />
        </div>
      ) : activeTab === 'eval' ? (
        /* ── Eval tab ── */
        <EvalTab />
      ) : (
        /* ── Tokens tab ── */
        <TokenReportPage />
      )}
    </div>
  )
}

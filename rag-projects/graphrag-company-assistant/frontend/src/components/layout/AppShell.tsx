import Header from './Header'
import ChatWindow from '../chat/ChatWindow'
import ChatInput from '../chat/ChatInput'
import RightPanel from './RightPanel'
import { useChatStore } from '../../store'

export default function AppShell() {
  const activeSources = useChatStore((s) => s.activeSources)
  const activeGraphData = useChatStore((s) => s.activeGraphData)

  const showPanel = activeSources.length > 0 || activeGraphData !== null

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-col flex-1 min-w-0">
          <ChatWindow />
          <ChatInput />
        </div>
        {showPanel && <RightPanel />}
      </div>
    </div>
  )
}

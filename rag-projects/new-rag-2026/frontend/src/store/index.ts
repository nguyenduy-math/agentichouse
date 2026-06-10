import { create } from 'zustand'
import type { ChatMessage, Source, AgentTraceResponse } from '../types/chat'

// ─── Chat store ───────────────────────────────────────────────────────────────
interface ChatStore {
  messages: ChatMessage[]
  isLoading: boolean
  activeSources: Source[]
  agentTrace: AgentTraceResponse | null
  traceOpen: boolean
  addMessage: (msg: ChatMessage) => void
  setLoading: (v: boolean) => void
  setActiveSources: (sources: Source[]) => void
  setAgentTrace: (trace: AgentTraceResponse | null) => void
  setTraceOpen: (v: boolean) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  isLoading: false,
  activeSources: [],
  agentTrace: null,
  traceOpen: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setLoading: (v) => set({ isLoading: v }),
  setActiveSources: (sources) => set({ activeSources: sources }),
  setAgentTrace: (trace) => set({ agentTrace: trace }),
  setTraceOpen: (v) => set({ traceOpen: v }),
  clearMessages: () =>
    set({ messages: [], activeSources: [], agentTrace: null }),
}))

// ─── Session store ────────────────────────────────────────────────────────────
interface SessionStore {
  sessionId: string | null
  llmProvider: string
  setSessionId: (id: string | null) => void
  setLlmProvider: (p: string) => void
}

export const useSessionStore = create<SessionStore>((set) => ({
  sessionId: null,
  llmProvider: 'gemini',
  setSessionId: (id) => set({ sessionId: id }),
  setLlmProvider: (p) => set({ llmProvider: p }),
}))

// ─── Tab store ────────────────────────────────────────────────────────────────
type Tab = 'chat' | 'admin' | 'eval' | 'tokens'

interface TabStore {
  activeTab: Tab
  setActiveTab: (t: Tab) => void
}

export const useTabStore = create<TabStore>((set) => ({
  activeTab: 'chat',
  setActiveTab: (t) => set({ activeTab: t }),
}))

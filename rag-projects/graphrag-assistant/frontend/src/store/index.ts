import { create } from 'zustand'
import type { Message, PolicySource, GraphData } from '../types/chat'

interface ChatStore {
  messages: Message[]
  isLoading: boolean
  activeSources: PolicySource[]
  activeGraphData: GraphData | null
  addMessage: (msg: Message) => void
  setLoading: (v: boolean) => void
  setActiveSources: (sources: PolicySource[]) => void
  setActiveGraphData: (data: GraphData | null) => void
  clearMessages: () => void
}

interface SessionStore {
  sessionId: string | null
  setSessionId: (id: string | null) => void
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  isLoading: false,
  activeSources: [],
  activeGraphData: null,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setLoading: (v) => set({ isLoading: v }),
  setActiveSources: (sources) => set({ activeSources: sources }),
  setActiveGraphData: (data) => set({ activeGraphData: data }),
  clearMessages: () => set({ messages: [], activeSources: [], activeGraphData: null }),
}))

export const useSessionStore = create<SessionStore>((set) => ({
  sessionId: null,
  setSessionId: (id) => set({ sessionId: id }),
}))

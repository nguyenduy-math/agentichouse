import { create } from 'zustand'

interface EvalStore {
  selectedSessionId: string | null
  selectedTurnIds: Set<string>
  selectedRunId: string | null
  compareRunId: string | null

  setSelectedSessionId: (id: string | null) => void
  toggleTurnId: (id: string) => void
  setSelectedTurnIds: (ids: string[]) => void
  clearTurnIds: () => void
  setSelectedRunId: (id: string | null) => void
  setCompareRunId: (id: string | null) => void
}

export const useEvalStore = create<EvalStore>((set) => ({
  selectedSessionId: null,
  selectedTurnIds: new Set(),
  selectedRunId: null,
  compareRunId: null,

  setSelectedSessionId: (id) =>
    set({ selectedSessionId: id, selectedTurnIds: new Set() }),

  toggleTurnId: (id) =>
    set((s) => {
      const next = new Set(s.selectedTurnIds)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return { selectedTurnIds: next }
    }),

  setSelectedTurnIds: (ids) => set({ selectedTurnIds: new Set(ids) }),

  clearTurnIds: () => set({ selectedTurnIds: new Set() }),

  setSelectedRunId: (id) => set({ selectedRunId: id }),

  setCompareRunId: (id) => set({ compareRunId: id }),
}))

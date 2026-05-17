import type { PolicySource } from '../../types/chat'
import SourceCard from './SourceCard'

interface Props {
  sources: PolicySource[]
}

export default function SourcesPanel({ sources }: Props) {
  return (
    <div className="h-full overflow-y-auto p-3 space-y-2">
      {sources.map((s, idx) => (
        <SourceCard key={`${s.source_file}-${s.page_number}-${idx}`} source={s} />
      ))}
    </div>
  )
}

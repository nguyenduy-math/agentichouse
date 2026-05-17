import { Building2 } from 'lucide-react'

export default function Header() {
  return (
    <header className="h-14 bg-blue-700 text-white flex items-center px-4 gap-3 shadow-md flex-shrink-0">
      <Building2 className="w-6 h-6" />
      <div>
        <h1 className="text-base font-semibold leading-tight">Trợ Lý Nội Quy Công Ty</h1>
        <p className="text-xs text-blue-200 leading-tight">Agentic House · GraphRAG · Neo4j</p>
      </div>
    </header>
  )
}

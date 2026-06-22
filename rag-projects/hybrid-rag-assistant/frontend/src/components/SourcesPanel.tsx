import { useState } from "react";
import { ChunkSource } from "../api/client";

const DOMAIN_COLORS: Record<string, string> = {
  hr: "bg-green-100 text-green-700",
  legal: "bg-purple-100 text-purple-700",
  finance: "bg-yellow-100 text-yellow-700",
  general: "bg-gray-100 text-gray-600",
};

function highlightText(text: string, query?: string): React.ReactNode[] {
  if (!query) return [<span key="all">{text}</span>];

  const keywords = query
    .split(/\s+/)
    .filter((w) => w.length > 2)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));

  if (keywords.length === 0) return [<span key="all">{text}</span>];

  const pattern = new RegExp(`(${keywords.join("|")})`, "gi");
  const parts = text.split(pattern);

  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="bg-yellow-200 text-yellow-900 rounded px-0.5 not-italic">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

interface Props {
  sources: ChunkSource[];
  rewrittenQuery?: string;
}

export default function SourcesPanel({ sources, rewrittenQuery }: Props) {
  const [open, setOpen] = useState(true);

  if (sources.length === 0) return null;

  return (
    <div className="border border-gray-200 rounded-lg bg-white text-sm">
      <button
        className="w-full flex justify-between items-center px-4 py-2 font-medium text-gray-700 hover:bg-gray-50 rounded-lg"
        onClick={() => setOpen((v) => !v)}
      >
        <span>Nguồn tham khảo ({sources.length})</span>
        <span className="text-gray-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="divide-y divide-gray-100">
          {sources.map((src, i) => (
            <div key={src.chunk_id} className="px-4 py-3">
              <div className="flex justify-between items-start mb-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-blue-700">
                    [{i + 1}] {src.source_file}
                  </span>
                  {src.domain && (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        DOMAIN_COLORS[src.domain] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {src.domain}
                    </span>
                  )}
                </div>
                <span className="text-xs text-gray-400 ml-2 shrink-0">
                  trang {src.page_number} · score {src.rerank_score.toFixed(3)}
                </span>
              </div>
              <p className="text-gray-600 leading-relaxed">
                {highlightText(src.excerpt, rewrittenQuery)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

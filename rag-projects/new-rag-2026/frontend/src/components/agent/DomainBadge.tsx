// Domain badge colors (dark-theme friendly)
export const DOMAIN_CONFIG: Record<
  string,
  { label: string; classes: string }
> = {
  hr: {
    label: 'Nhân sự',
    classes: 'bg-blue-900/60 text-blue-300 border border-blue-700',
  },
  benefits: {
    label: 'Phúc lợi',
    classes: 'bg-green-900/60 text-green-300 border border-green-700',
  },
  it: {
    label: 'Bảo mật CNTT',
    classes: 'bg-purple-900/60 text-purple-300 border border-purple-700',
  },
  finance: {
    label: 'Tài chính',
    classes: 'bg-amber-900/60 text-amber-300 border border-amber-700',
  },
  compliance: {
    label: 'Tuân thủ',
    classes: 'bg-red-900/60 text-red-300 border border-red-700',
  },
  procedures: {
    label: 'Quy trình',
    classes: 'bg-teal-900/60 text-teal-300 border border-teal-700',
  },
  general: {
    label: 'Tổng hợp',
    classes: 'bg-slate-700/60 text-slate-300 border border-slate-600',
  },
}

interface Props {
  domainKey: string
  size?: 'sm' | 'xs'
}

export default function DomainBadge({ domainKey, size = 'xs' }: Props) {
  const config = DOMAIN_CONFIG[domainKey] ?? {
    label: domainKey,
    classes: 'bg-slate-700/60 text-slate-300 border border-slate-600',
  }
  const textSize = size === 'xs' ? 'text-[10px]' : 'text-xs'
  return (
    <span
      className={`inline-flex items-center ${textSize} font-medium px-1.5 py-0.5 rounded-full ${config.classes}`}
    >
      {config.label}
    </span>
  )
}

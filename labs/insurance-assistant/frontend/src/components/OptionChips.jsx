export default function OptionChips({ options, onSelect }) {
  if (!options || options.length === 0) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, padding: '4px 0 12px 40px' }}>
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => onSelect(opt)}
          style={{
            padding: '6px 14px',
            background: '#eff6ff',
            border: '1px solid #93c5fd',
            borderRadius: 20,
            color: '#1d4ed8',
            fontSize: 13,
            cursor: 'pointer',
            fontWeight: 500,
            transition: 'background 0.15s',
          }}
          onMouseEnter={e => (e.currentTarget.style.background = '#dbeafe')}
          onMouseLeave={e => (e.currentTarget.style.background = '#eff6ff')}
        >
          {opt}
        </button>
      ))}
    </div>
  )
}

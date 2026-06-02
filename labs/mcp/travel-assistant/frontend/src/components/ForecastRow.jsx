import { getWeatherEmoji } from './WeatherCard.jsx'

const DAY_NAMES = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']

function dayName(dateStr) {
  try {
    const d = new Date(dateStr + 'T12:00:00')
    return DAY_NAMES[d.getDay()]
  } catch {
    return dateStr
  }
}

export default function ForecastRow({ forecast }) {
  if (!forecast || forecast.length === 0) return null

  return (
    <div style={styles.card}>
      <div style={styles.header}>📅 Dự báo 5 ngày</div>
      <div style={styles.row}>
        {forecast.map((day, i) => (
          <div key={i} style={styles.tile}>
            <div style={styles.day}>{dayName(day.date)}</div>
            <div style={{ fontSize: '1.6rem' }}>{getWeatherEmoji(day.condition)}</div>
            <div style={styles.temps}>
              <span style={{ color: '#f87171' }}>{day.temp_max != null ? `${day.temp_max}°` : '—'}</span>
              {' / '}
              <span style={{ color: '#60a5fa' }}>{day.temp_min != null ? `${day.temp_min}°` : '—'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const styles = {
  card: {
    background: '#1a1d27',
    border: '1px solid #2a2d3a',
    borderRadius: '14px',
    padding: '1.25rem 1.5rem',
  },
  header: {
    fontSize: '0.9rem',
    fontWeight: 600,
    color: '#7a7f9a',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '1rem',
  },
  row: {
    display: 'flex',
    gap: '0.5rem',
    overflowX: 'auto',
  },
  tile: {
    flex: '1 0 70px',
    background: '#0f1117',
    border: '1px solid #2a2d3a',
    borderRadius: '10px',
    padding: '0.75rem 0.5rem',
    textAlign: 'center',
    minWidth: '70px',
  },
  day: {
    fontSize: '0.8rem',
    fontWeight: 600,
    color: '#7a7f9a',
    marginBottom: '0.3rem',
  },
  temps: {
    fontSize: '0.85rem',
    marginTop: '0.3rem',
    color: '#e8eaf0',
  },
}

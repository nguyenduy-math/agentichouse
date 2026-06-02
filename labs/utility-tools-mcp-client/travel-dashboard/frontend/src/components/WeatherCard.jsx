const CONDITION_EMOJI = [
  ['thunder', '⛈️'],
  ['snow', '🌨️'],
  ['sleet', '🌨️'],
  ['drizzle', '🌦️'],
  ['rain', '🌧️'],
  ['shower', '🌧️'],
  ['fog', '🌫️'],
  ['mist', '🌫️'],
  ['overcast', '☁️'],
  ['cloud', '⛅'],
  ['partly', '⛅'],
  ['mainly clear', '🌤️'],
  ['mostly', '🌤️'],
  ['clear', '☀️'],
  ['sunny', '☀️'],
]

export function getWeatherEmoji(condition = '') {
  const c = condition.toLowerCase()
  for (const [kw, emoji] of CONDITION_EMOJI) {
    if (c.includes(kw)) return emoji
  }
  return '🌡️'
}

function tempColor(temp) {
  if (temp == null) return '#e8eaf0'
  if (temp <= 15) return '#60a5fa'
  if (temp <= 28) return '#fbbf24'
  return '#f87171'
}

export default function WeatherCard({ weather, city }) {
  const { temperature, condition, humidity, wind_speed } = weather

  return (
    <div style={styles.card}>
      <div style={styles.header}>🌡️ Thời tiết hiện tại — {city}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', margin: '1rem 0' }}>
        <span style={{ fontSize: '3rem' }}>{getWeatherEmoji(condition)}</span>
        <span style={{ fontSize: '3.5rem', fontWeight: 700, color: tempColor(temperature) }}>
          {temperature != null ? `${temperature}°C` : '—'}
        </span>
      </div>
      <div style={styles.condition}>{condition || '—'}</div>
      <div style={styles.stats}>
        {humidity != null && <span>💧 {humidity}%</span>}
        {wind_speed != null && <span>💨 {wind_speed} km/h</span>}
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
  },
  condition: {
    color: '#e8eaf0',
    fontSize: '1rem',
    marginBottom: '0.75rem',
  },
  stats: {
    display: 'flex',
    gap: '1.5rem',
    color: '#7a7f9a',
    fontSize: '0.9rem',
  },
}

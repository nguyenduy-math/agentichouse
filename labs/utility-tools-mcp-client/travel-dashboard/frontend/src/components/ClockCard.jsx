import { useState, useEffect } from 'react'

function pad(n) {
  return String(n).padStart(2, '0')
}

function getLocalTime(utcOffsetHours) {
  const now = new Date()
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000
  const cityMs = utcMs + utcOffsetHours * 3600000
  return new Date(cityMs)
}

export default function ClockCard({ localTime, city }) {
  const offset = localTime?.utc_offset_hours ?? 0
  const timezone = localTime?.timezone ?? ''

  const [time, setTime] = useState(() => getLocalTime(offset))

  useEffect(() => {
    const id = setInterval(() => setTime(getLocalTime(offset)), 1000)
    return () => clearInterval(id)
  }, [offset])

  const h = pad(time.getUTCHours())
  const m = pad(time.getUTCMinutes())
  const s = pad(time.getUTCSeconds())
  const dateStr = time.toLocaleDateString('vi-VN', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    timeZone: 'UTC',
  })

  return (
    <div style={styles.card}>
      <div style={styles.header}>🕐 Giờ địa phương — {city}</div>
      <div style={styles.clock}>{h}:{m}:{s}</div>
      <div style={styles.date}>{dateStr}</div>
      {timezone && <div style={styles.tz}>{timezone} (UTC{offset >= 0 ? '+' : ''}{offset})</div>}
    </div>
  )
}

const styles = {
  card: {
    background: '#1a1d27',
    border: '1px solid #2a2d3a',
    borderRadius: '14px',
    padding: '1.25rem 1.5rem',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
  },
  header: {
    fontSize: '0.9rem',
    fontWeight: 600,
    color: '#7a7f9a',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '1rem',
  },
  clock: {
    fontFamily: "'Courier New', monospace",
    fontSize: '2.8rem',
    fontWeight: 700,
    color: '#4f8ef7',
    letterSpacing: '0.05em',
    margin: '0.5rem 0',
  },
  date: {
    color: '#e8eaf0',
    fontSize: '0.95rem',
    marginBottom: '0.25rem',
  },
  tz: {
    color: '#7a7f9a',
    fontSize: '0.8rem',
  },
}

import { useState, useEffect } from 'react'

// Verify the timezone is one the browser's Intl actually supports; fall back to
// the viewer's local zone if the API gave us something unusable.
function resolveTimeZone(tz) {
  if (!tz) return undefined
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz })
    return tz
  } catch {
    return undefined
  }
}

// Current UTC offset for an IANA zone (DST-aware), formatted like "UTC+7" / "UTC+5:30".
function offsetLabel(timeZone, date) {
  try {
    const name = new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'shortOffset' })
      .formatToParts(date)
      .find(p => p.type === 'timeZoneName')?.value
    return name ? name.replace('GMT', 'UTC') : ''
  } catch {
    return ''
  }
}

export default function ClockCard({ localTime, city }) {
  // Drive the clock from the destination's IANA timezone — not the (unreliable)
  // numeric offset — so DST is handled correctly.
  const timeZone = resolveTimeZone(localTime?.timezone)
  const tzId = localTime?.timezone || ''

  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const timeStr = now.toLocaleTimeString('vi-VN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone,
  })
  const dateStr = now.toLocaleDateString('vi-VN', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZone,
  })
  const label = timeZone ? offsetLabel(timeZone, now) : ''

  return (
    <div style={styles.card}>
      <div style={styles.header}>🕐 Giờ địa phương — {city}</div>
      <div style={styles.clock}>{timeStr}</div>
      <div style={styles.date}>{dateStr}</div>
      {tzId && <div style={styles.tz}>{tzId}{label && ` (${label})`}</div>}
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

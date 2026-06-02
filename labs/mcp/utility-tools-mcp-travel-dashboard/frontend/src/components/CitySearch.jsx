import { useState } from 'react'

export default function CitySearch({ onSearch, loading }) {
  const [city, setCity] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (city.trim()) onSearch(city.trim())
  }

  return (
    <form onSubmit={handleSubmit} style={styles.form}>
      <input
        type="text"
        value={city}
        onChange={e => setCity(e.target.value)}
        placeholder="Nhập thành phố… (VD: Tokyo, Paris, Hanoi)"
        style={styles.input}
        disabled={loading}
      />
      <button type="submit" disabled={loading || !city.trim()} style={styles.button}>
        {loading ? '⏳' : '🔍 Tìm kiếm'}
      </button>
    </form>
  )
}

const styles = {
  form: {
    display: 'flex',
    gap: '0.75rem',
    marginBottom: '2rem',
    flexWrap: 'wrap',
  },
  input: {
    flex: 1,
    minWidth: '220px',
    padding: '0.75rem 1rem',
    borderRadius: '10px',
    border: '1px solid #2a2d3a',
    background: '#1a1d27',
    color: '#e8eaf0',
    fontSize: '1rem',
    outline: 'none',
  },
  button: {
    padding: '0.75rem 1.5rem',
    borderRadius: '10px',
    border: 'none',
    background: '#4f8ef7',
    color: '#fff',
    fontSize: '1rem',
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
}

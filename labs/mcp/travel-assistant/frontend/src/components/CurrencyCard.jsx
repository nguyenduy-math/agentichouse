import { useState, useEffect } from 'react'
import { convertCurrency, getRate } from '../api.js'

const CURRENCIES = ['VND', 'USD', 'EUR', 'JPY', 'GBP', 'CNY', 'KRW', 'THB', 'SGD', 'AUD', 'CAD']

export default function CurrencyCard({ defaultToCurrency = 'USD', city }) {
  const [from, setFrom] = useState('VND')
  const [to, setTo] = useState(defaultToCurrency !== 'VND' ? defaultToCurrency : 'USD')
  const [amount, setAmount] = useState(1000000)
  const [result, setResult] = useState(null)
  const [rate, setRate] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const newTo = defaultToCurrency !== 'VND' ? defaultToCurrency : 'USD'
    setTo(newTo)
    setResult(null)
    loadRate('VND', newTo)
  }, [defaultToCurrency])

  async function loadRate(f, t) {
    try {
      const data = await getRate(f, t)
      setRate(data.rate)
    } catch {
      setRate(null)
    }
  }

  async function handleConvert() {
    setLoading(true)
    setError(null)
    try {
      const data = await convertCurrency(from, to, amount)
      setResult(data.converted)
      if (data.rate) setRate(data.rate)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.card}>
      <div style={styles.header}>💱 Tỷ giá — {city}</div>
      <div style={styles.row}>
        <input
          type="number"
          value={amount}
          onChange={e => setAmount(Number(e.target.value))}
          style={styles.input}
          min={0}
        />
        <select value={from} onChange={e => setFrom(e.target.value)} style={styles.select}>
          {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <span style={{ color: '#7a7f9a', fontSize: '1.2rem' }}>→</span>
        <select value={to} onChange={e => setTo(e.target.value)} style={styles.select}>
          {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <button onClick={handleConvert} disabled={loading} style={styles.button}>
          {loading ? '⏳' : 'Chuyển đổi'}
        </button>
      </div>

      {error && <div style={styles.error}>{error}</div>}

      {result != null && (
        <div style={styles.result}>
          {amount.toLocaleString('vi-VN')} {from} ={' '}
          <span style={styles.resultValue}>
            {result.toLocaleString('vi-VN', { maximumFractionDigits: 2 })} {to}
          </span>
        </div>
      )}

      {rate != null && (
        <div style={styles.rateInfo}>
          1 {from} = {rate.toLocaleString('vi-VN', { maximumFractionDigits: 6 })} {to}
        </div>
      )}
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
    flexWrap: 'wrap',
    gap: '0.5rem',
    alignItems: 'center',
  },
  input: {
    width: '140px',
    padding: '0.6rem 0.75rem',
    borderRadius: '8px',
    border: '1px solid #2a2d3a',
    background: '#0f1117',
    color: '#e8eaf0',
    fontSize: '1rem',
  },
  select: {
    padding: '0.6rem 0.75rem',
    borderRadius: '8px',
    border: '1px solid #2a2d3a',
    background: '#0f1117',
    color: '#e8eaf0',
    fontSize: '1rem',
    cursor: 'pointer',
  },
  button: {
    padding: '0.6rem 1.25rem',
    borderRadius: '8px',
    border: 'none',
    background: '#4f8ef7',
    color: '#fff',
    fontSize: '0.95rem',
    fontWeight: 600,
    cursor: 'pointer',
  },
  result: {
    marginTop: '1rem',
    fontSize: '1.1rem',
    color: '#e8eaf0',
  },
  resultValue: {
    color: '#4f8ef7',
    fontWeight: 700,
    fontSize: '1.3rem',
  },
  rateInfo: {
    marginTop: '0.4rem',
    color: '#7a7f9a',
    fontSize: '0.85rem',
  },
  error: {
    marginTop: '0.75rem',
    color: '#f87171',
    fontSize: '0.9rem',
  },
}

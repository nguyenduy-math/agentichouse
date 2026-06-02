import { useState } from 'react'
import { travelSearch } from './api.js'
import CitySearch from './components/CitySearch.jsx'
import WeatherCard from './components/WeatherCard.jsx'
import ForecastRow from './components/ForecastRow.jsx'
import ClockCard from './components/ClockCard.jsx'
import CurrencyCard from './components/CurrencyCard.jsx'
import ChatPanel from './components/ChatPanel.jsx'

const globalStyle = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f1117; color: #e8eaf0; font-family: system-ui, -apple-system, sans-serif; }
  input, select, button { font-family: inherit; }
  input[type=number]::-webkit-inner-spin-button { opacity: 1; }
`

export default function App() {
  const [travelData, setTravelData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSearch(city) {
    setLoading(true)
    setError(null)
    setTravelData(null)
    try {
      const data = await travelSearch(city)
      setTravelData(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <style>{globalStyle}</style>
      <div style={styles.container}>
        <header style={styles.header}>
          <h1 style={styles.title}>✈️ Travel Dashboard</h1>
          <p style={styles.subtitle}>Thời tiết · Giờ địa phương · Tỷ giá</p>
        </header>

        <CitySearch onSearch={handleSearch} loading={loading} />

        {error && (
          <div style={styles.errorBanner}>
            ⚠️ {error}
          </div>
        )}

        {loading && (
          <div style={styles.loadingBanner}>
            ⏳ Đang tải dữ liệu cho {' '}
            <strong style={{ color: '#4f8ef7' }}>...</strong>
          </div>
        )}

        {travelData && (
          <>
            <div style={styles.tripInfo}>
              🌍 {travelData.city}
              {travelData.timezone && ` · ${travelData.timezone}`}
              {travelData.local_currency && travelData.local_currency !== 'VND' &&
                ` · Đơn vị tiền: ${travelData.local_currency}`}
            </div>

            <div style={styles.topGrid}>
              <WeatherCard weather={travelData.weather} city={travelData.city} />
              <ClockCard localTime={travelData.local_time} city={travelData.city} />
            </div>

            <ForecastRow forecast={travelData.forecast} />

            <CurrencyCard
              defaultToCurrency={travelData.local_currency || 'USD'}
              city={travelData.city}
            />
          </>
        )}

        <ChatPanel city={travelData?.city} />
      </div>
    </>
  )
}

const styles = {
  container: {
    maxWidth: '900px',
    margin: '0 auto',
    padding: '2rem 1.25rem',
  },
  header: {
    marginBottom: '2rem',
    textAlign: 'center',
  },
  title: {
    fontSize: '2rem',
    fontWeight: 700,
    color: '#e8eaf0',
  },
  subtitle: {
    color: '#7a7f9a',
    marginTop: '0.3rem',
    fontSize: '0.95rem',
  },
  errorBanner: {
    background: '#3b1a1a',
    border: '1px solid #7f1d1d',
    color: '#f87171',
    borderRadius: '10px',
    padding: '0.75rem 1rem',
    marginBottom: '1.5rem',
    fontSize: '0.95rem',
  },
  loadingBanner: {
    color: '#7a7f9a',
    textAlign: 'center',
    padding: '2rem',
    fontSize: '1rem',
  },
  tripInfo: {
    background: '#1a1d27',
    border: '1px solid #2a2d3a',
    borderRadius: '10px',
    padding: '0.75rem 1rem',
    marginBottom: '1.25rem',
    color: '#e8eaf0',
    fontSize: '0.95rem',
  },
  topGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
    gap: '1.25rem',
    marginBottom: '1.25rem',
  },
}

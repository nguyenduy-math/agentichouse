const BASE = '/api'

export async function travelSearch(city) {
  const res = await fetch(`${BASE}/travel?city=${encodeURIComponent(city)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Unknown error')
  }
  return res.json()
}

export async function convertCurrency(from, to, amount) {
  const res = await fetch(
    `${BASE}/currency?from=${from}&to=${to}&amount=${amount}`
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Unknown error')
  }
  return res.json()
}

export async function getRate(from, to) {
  const res = await fetch(`${BASE}/rate?from=${from}&to=${to}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Unknown error')
  }
  return res.json()
}

# Travel Dashboard — Implementation Plan

**Status:** Planning  
**Target:** Single-page Travel Dashboard web app backed by the `utility-tools-mcp` Java server  
**Date:** 2026-06-02

---

## 1. Overview

The Travel Dashboard is a single-page web application where a user types a destination city and instantly sees a rich information panel: current weather and a 5-day forecast, the local clock ticking in real time, a currency converter pre-loaded with VND as the home currency, and a trip-info summary drawn from the data. The interface uses Vietnamese labels where natural (Thời tiết, Tỷ giá, Giờ địa phương) and is styled as a dark, card-based travel app.

### Why Option A (FastAPI bridge) is recommended

The `utility-tools-mcp` server communicates exclusively over **stdio** using JSON-RPC. A browser-based React app cannot open a subprocess or write to stdin/stdout, so a thin server-side bridge is required. A Python **FastAPI** process fills that role: it spawns the Java jar as a subprocess, speaks the MCP JSON-RPC protocol over its stdin/stdout, and exposes clean REST endpoints to the React frontend. This keeps the MCP server fully in the loop (the point of the exercise), adds no unnecessary complexity, and stays in the same language ecosystem the team already uses for scripting.

### User experience in one paragraph

The user lands on a dark dashboard page. A single search bar at the top reads "Nhập thành phố…". They type "Tokyo" and press Search. Four cards materialize simultaneously: a **Thời tiết** card showing 22 °C with a partly-cloudy emoji, a 5-day forecast strip below it, a **Giờ địa phương** card with a large digital clock counting seconds in real time, and a **Tỷ giá** card pre-loaded with VND ↔ JPY so they can type an amount and see the conversion live. A narrow **Trip Info** ribbon at the bottom surfaces one-liner fun facts derived from the data (e.g., "Tokyo is 2 hours ahead of Hanoi · 1 JPY ≈ 165 VND").

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser                                                        │
│                                                                 │
│  React (Vite, port 5173)                                        │
│  CitySearch → WeatherCard, ForecastRow, ClockCard, CurrencyCard │
└───────────────────────┬─────────────────────────────────────────┘
                        │  HTTP REST (fetch / axios)
                        │  GET /api/travel?city=Tokyo
                        │  GET /api/currency?from=VND&to=JPY&amount=1000000
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI bridge  (Python, port 8000)                            │
│                                                                 │
│  main.py          — REST endpoints, response assembly           │
│  mcp_client.py    — stdio JSON-RPC client for the Java jar      │
└───────────────────────┬─────────────────────────────────────────┘
                        │  stdin / stdout  (JSON-RPC 2.0)
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Java MCP server  (utility-tools-mcp-0.0.1.jar)                 │
│                                                                 │
│  geocode · get_weather · get_forecast                           │
│  current_time · convert_currency · get_exchange_rate            │
└───────────────────────┬─────────────────────────────────────────┘
                        │  HTTPS
                        ▼
        Open-Meteo API          ExchangeRate-API (open, no key)
```

---

## 3. Project Structure

```
utility-tools-mcp-client/
├── travel-dashboard/
│   ├── backend/
│   │   ├── main.py              # FastAPI app — REST endpoints
│   │   ├── mcp_client.py        # Subprocess + stdio JSON-RPC client
│   │   ├── requirements.txt
│   │   └── .env.example         # MCP_JAR_PATH and optional settings
│   └── frontend/
│       ├── index.html
│       ├── package.json
│       ├── vite.config.js       # proxy /api → localhost:8000
│       └── src/
│           ├── App.jsx           # root layout, state, search handler
│           ├── api.js            # fetch helpers (travelSearch, convertCurrency)
│           └── components/
│               ├── CitySearch.jsx
│               ├── WeatherCard.jsx
│               ├── ForecastRow.jsx
│               ├── ClockCard.jsx
│               └── CurrencyCard.jsx
└── PLAN_TRAVEL_DASHBOARD.md     # this file
```

---

## 4. MCP Bridge Design — `mcp_client.py`

### Responsibilities

- Spawn `java -jar <jar>` as a long-lived subprocess (one instance per FastAPI process).
- Send JSON-RPC requests over the subprocess's **stdin**.
- Read newline-delimited JSON responses from **stdout**.
- Maintain a monotonically increasing request `id` counter.
- Issue the MCP `initialize` handshake once at startup before any tool calls.
- Parse the `result.content[0].text` field from each tool response.

### Subprocess lifecycle

```python
# mcp_client.py  (outline)
import asyncio, json, os, sys
from pathlib import Path

JAR_PATH = os.environ.get("MCP_JAR_PATH",
    "../../utility-tools-mcp/target/utility-tools-mcp-0.0.1.jar")

class MCPClient:
    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._id = 0
        self._lock = asyncio.Lock()

    async def start(self):
        self._proc = await asyncio.create_subprocess_exec(
            "java", "-jar", str(Path(JAR_PATH).resolve()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,   # captures MCP server logs
        )
        await self._initialize()

    async def _send(self, method: str, params: dict) -> dict:
        async with self._lock:          # serialize requests
            self._id += 1
            msg = json.dumps({
                "jsonrpc": "2.0",
                "id": self._id,
                "method": method,
                "params": params,
            }) + "\n"
            self._proc.stdin.write(msg.encode())
            await self._proc.stdin.drain()
            raw = await self._proc.stdout.readline()
            return json.loads(raw)

    async def _initialize(self):
        await self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "travel-dashboard-bridge", "version": "1.0"},
        })

    async def call_tool(self, name: str, arguments: dict) -> str:
        response = await self._send("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        # MCP response shape: {"result": {"content": [{"type":"text","text":"..."}]}}
        return response["result"]["content"][0]["text"]

    async def stop(self):
        if self._proc:
            self._proc.stdin.close()
            await self._proc.wait()

# Singleton — created at FastAPI startup
mcp = MCPClient()
```

### Key implementation notes

- The Java server writes all logs to `./mcp-server.log` (not stdout), so stdout is a clean JSON-RPC channel. Capture stderr separately to avoid blocking.
- The `_lock` ensures only one request is in-flight at a time (the stdio channel is not multiplexed). For true concurrency, run multiple subprocess instances behind a pool.
- If the subprocess dies, FastAPI startup should fail fast with a clear error message.

---

## 5. FastAPI Endpoints — `main.py`

### Startup / shutdown

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp_client import mcp
import asyncio, json

@asynccontextmanager
async def lifespan(app: FastAPI):
    await mcp.start()
    yield
    await mcp.stop()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
```

### `GET /api/travel?city={city}`

Orchestrates the full lookup for a city. Steps:
1. Call `geocode(location=city)` → parse `lat`, `lon`, `timezone` from result text.
2. Fan out three MCP calls **in parallel** using `asyncio.gather`:
   - `get_weather(latitude=lat, longitude=lon)`
   - `get_forecast(latitude=lat, longitude=lon)`
   - `current_time(timezone=timezone)`
3. Parse and combine into a single response.

**Response schema:**
```json
{
  "city": "Tokyo",
  "lat": 35.6895,
  "lon": 139.6917,
  "timezone": "Asia/Tokyo",
  "weather": {
    "temperature": 22.1,
    "condition": "Partly cloudy",
    "humidity": 65,
    "wind_speed": 14.2,
    "wind_unit": "km/h"
  },
  "forecast": [
    { "date": "2026-06-02", "condition": "Sunny", "temp_max": 25.0, "temp_min": 18.0 },
    { "date": "2026-06-03", "condition": "Rainy",  "temp_max": 21.0, "temp_min": 16.0 }
    // ... 5 days total
  ],
  "local_time": {
    "datetime": "2026-06-02T20:45:00",
    "timezone": "Asia/Tokyo",
    "utc_offset_hours": 9
  }
}
```

### `GET /api/currency?from={from}&to={to}&amount={amount}`

Calls `convert_currency(amount, from_currency, to_currency)`.

**Response schema:**
```json
{
  "from": "VND",
  "to": "JPY",
  "amount": 1000000,
  "converted": 6060.6,
  "rate": 0.00000606
}
```

### `GET /api/rate?from={from}&to={to}`

Calls `get_exchange_rate(from_currency, to_currency)`.

**Response schema:**
```json
{
  "from": "USD",
  "to": "VND",
  "rate": 25400.0,
  "updated": "2026-06-02"
}
```

### Error handling

Return HTTP 400 for bad city names (geocode returns no results) and HTTP 503 if the MCP subprocess is unreachable. Always include an `"error"` string field in the JSON body.

---

## 6. Frontend Components

### `api.js`

```js
const BASE = "/api";   // Vite proxies /api → localhost:8000

export async function travelSearch(city) {
  const res = await fetch(`${BASE}/travel?city=${encodeURIComponent(city)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function convertCurrency(from, to, amount) {
  const res = await fetch(
    `${BASE}/currency?from=${from}&to=${to}&amount=${amount}`
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getRate(from, to) {
  const res = await fetch(`${BASE}/rate?from=${from}&to=${to}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

### `App.jsx`

Root component. Holds all state: `travelData`, `loading`, `error`, and `city` input. On search, calls `travelSearch(city)` and stores result. Renders the four cards only when data is available.

```
App
 ├── CitySearch          (always visible)
 ├── WeatherCard         (visible when travelData)
 ├── ForecastRow         (visible when travelData)
 ├── ClockCard           (visible when travelData)
 └── CurrencyCard        (visible when travelData, receives timezone info)
```

### `CitySearch.jsx`

- A controlled text input + "Tìm kiếm" button.
- Shows a spinner inside the button while `loading`.
- On Enter key or button click, calls `onSearch(city)` prop.

Props: `onSearch(city: string)`, `loading: bool`

### `WeatherCard.jsx`

Displays current weather for the searched city.

- Large temperature number (colored: blue ≤ 15 °C, yellow 15–28 °C, red ≥ 28 °C)
- Condition emoji (see Section 7) + condition text
- Two secondary stats: humidity (💧 %), wind speed (💨 km/h)
- Card header: "🌡️ Thời tiết hiện tại — {city}"

Props: `weather: object`, `city: string`

### `ForecastRow.jsx`

A horizontal strip of 5 day-tiles.

Each tile shows:
- Short day name (Mon, Tue … derived from `date` field)
- Condition emoji
- High / low temps in a `25° / 18°` format

Props: `forecast: array`

### `ClockCard.jsx`

Shows the local time in the destination city, ticking every second.

Implementation logic:
1. Receive `utc_offset_hours` from the API (e.g., `9` for Tokyo).
2. On mount, compute `displayTime = new Date(Date.now() + (utc_offset_hours - localOffset) * 3600000)`.
3. `setInterval` every 1 000 ms to update the displayed time.
4. Clear interval on unmount.
5. Format as `HH:MM:SS` in a large monospace font.
6. Show date below the clock.

Props: `localTime: { datetime, timezone, utc_offset_hours }`, `city: string`

Card header: "🕐 Giờ địa phương — {city}"

### `CurrencyCard.jsx`

- Amount input (number, default 1 000 000).
- From/to dropdowns, pre-set to `VND` ↔ destination currency (JPY / USD / EUR — detected from geocoded country).
- "Chuyển đổi" button calls `convertCurrency` and displays the result.
- Shows the live rate line: `1 USD = 25,400 VND` in small text below the result.

Props: `defaultToCurrency: string` (e.g., `"JPY"` for Tokyo), `city: string`

---

## 7. UI Design Spec

### Color palette (CSS variables)

```css
--bg: #0f1117;
--card-bg: #1a1d27;
--card-border: #2a2d3a;
--accent: #4f8ef7;
--text-primary: #e8eaf0;
--text-muted: #7a7f9a;
--temp-cold: #60a5fa;    /* ≤ 15 °C */
--temp-warm: #fbbf24;    /* 15–28 °C */
--temp-hot: #f87171;     /* ≥ 28 °C */
```

### Layout

- Single-column on mobile (< 768 px), two-column grid on desktop.
- Search bar spans full width at the top.
- WeatherCard + ClockCard side by side (desktop), stacked (mobile).
- ForecastRow spans full width below.
- CurrencyCard full width at the bottom.

### Weather condition → emoji mapping

| Condition keyword | Emoji |
|---|---|
| Clear / Sunny | ☀️ |
| Mainly clear / Mostly sunny | 🌤️ |
| Partly cloudy | ⛅ |
| Overcast / Cloudy | ☁️ |
| Drizzle / Light rain | 🌦️ |
| Rain / Showers | 🌧️ |
| Thunderstorm | ⛈️ |
| Snow / Sleet | 🌨️ |
| Fog / Mist | 🌫️ |

Map by checking `condition.toLowerCase()` for these substrings in order (most specific first).

### Typography

- City name / card titles: `font-weight: 600`, 1.1 rem
- Current temperature: `font-size: 3.5rem`, `font-weight: 700`
- Clock time: `font-family: 'Courier New', monospace`, `font-size: 2.8rem`
- Secondary stats: `color: var(--text-muted)`, 0.9 rem

---

## 8. Data Flow for a City Search

**Scenario:** user types "Tokyo" and clicks "Tìm kiếm".

```
1. User clicks search
   └─ App.jsx calls travelSearch("Tokyo")
   └─ Sets loading = true

2. Frontend  →  GET /api/travel?city=Tokyo  →  FastAPI bridge

3. Bridge: mcp.call_tool("geocode", {"location": "Tokyo"})
   └─ Java MCP server calls Open-Meteo geocoding API
   └─ Returns: "Tokyo, Japan · lat=35.6895, lon=139.6917, timezone=Asia/Tokyo"
   └─ Bridge parses lat, lon, timezone from text

4. Bridge fans out THREE parallel MCP calls (asyncio.gather):
   ├─ mcp.call_tool("get_weather",  {"latitude": 35.6895, "longitude": 139.6917})
   ├─ mcp.call_tool("get_forecast", {"latitude": 35.6895, "longitude": 139.6917})
   └─ mcp.call_tool("current_time", {"timezone": "Asia/Tokyo"})

5. Each call goes:
   FastAPI bridge → stdin of Java jar → Java calls external API → stdout back to bridge

6. Bridge assembles combined JSON response and returns it.

7. Frontend receives JSON
   └─ App.jsx stores travelData, sets loading = false
   └─ React renders WeatherCard, ForecastRow, ClockCard simultaneously
   └─ ClockCard starts its setInterval tick

8. CurrencyCard auto-loads the VND ↔ JPY rate
   └─ Calls GET /api/rate?from=VND&to=JPY on mount
   └─ Displays pre-loaded rate; user can type an amount to convert on demand
```

---

## 9. MCP JSON-RPC Protocol Detail

The Java server speaks [MCP spec 2024-11-05](https://modelcontextprotocol.io/specification) over newline-delimited JSON-RPC 2.0 on stdio.

### Message format

**Initialize (must be first message):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "travel-dashboard-bridge",
      "version": "1.0"
    }
  }
}
```

**Initialize response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": { "tools": {} },
    "serverInfo": { "name": "utility-tools-mcp", "version": "0.0.1" }
  }
}
```

**Call a tool:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "geocode",
    "arguments": {
      "location": "Tokyo"
    }
  }
}
```

**Tool response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Tokyo, Japan · lat=35.6895, lon=139.6917, timezone=Asia/Tokyo"
      }
    ],
    "isError": false
  }
}
```

**Extracting the result:**
```python
result_text = response["result"]["content"][0]["text"]
```

### Other tool argument shapes

```json
// get_weather / get_forecast
{ "latitude": 35.6895, "longitude": 139.6917 }

// current_time
{ "timezone": "Asia/Tokyo" }

// convert_currency
{ "amount": 1000000, "from_currency": "VND", "to_currency": "JPY" }

// get_exchange_rate
{ "from_currency": "USD", "to_currency": "VND" }
```

### stdio gotcha

The Java server disables the Spring Boot banner and routes all logs to `./mcp-server.log`. **Do not** write anything to stdout from tool code. The bridge must capture `stderr` to a separate buffer to avoid blocking the subprocess.

---

## 10. Environment / Config

### `.env.example`

```ini
# Path to the utility-tools-mcp fat jar (relative to backend/)
MCP_JAR_PATH=../../utility-tools-mcp/target/utility-tools-mcp-0.0.1.jar

# Optional: host/port overrides
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
```

### `requirements.txt`

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
python-dotenv>=1.0.0
```

### `package.json` (frontend)

Key dependencies:
```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.0.0"
  }
}
```

### `vite.config.js` — proxy so the frontend never hard-codes the backend URL

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
```

---

## 11. Getting Started

### Prerequisites

- Java 21+, Maven 3.6.3+
- Python 3.11+
- Node 20+, npm

### Step 1 — Build the MCP server jar

```bash
cd ../utility-tools-mcp
mvn clean package
# produces target/utility-tools-mcp-0.0.1.jar
```

### Step 2 — Start the FastAPI bridge

```bash
cd travel-dashboard/backend
cp .env.example .env          # adjust MCP_JAR_PATH if needed
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/api/travel?city=Hanoi`

### Step 3 — Start the React frontend

```bash
cd travel-dashboard/frontend
npm install
npm run dev
# opens http://localhost:5173
```

### Step 4 — Open the dashboard

Navigate to `http://localhost:5173`. Type a city name and press Search.

---

## 12. Implementation Order

Follow this sequence — each step is testable before starting the next.

1. **`mcp_client.py`** — implement `MCPClient.start()`, `call_tool()`, and the initialize handshake. Test by running a standalone Python script that calls `geocode("Hanoi")` and prints the result.

2. **`main.py` — `/api/travel` endpoint** — hardcode city for now. Test:
   ```bash
   curl "http://localhost:8000/api/travel?city=Tokyo"
   ```

3. **`main.py` — `/api/currency` and `/api/rate` endpoints** — test:
   ```bash
   curl "http://localhost:8000/api/currency?from=VND&to=USD&amount=1000000"
   curl "http://localhost:8000/api/rate?from=USD&to=VND"
   ```

4. **`CitySearch.jsx`** — build the input + button, wire the `onSearch` prop in `App.jsx`. Confirm the fetch hits the bridge and logs the JSON in the browser console.

5. **`WeatherCard.jsx`** — render static data first, then wire to live response. Confirm temperature coloring logic.

6. **`ForecastRow.jsx`** — render the 5-day strip. Verify day-name derivation from date strings.

7. **`ClockCard.jsx`** — implement the `setInterval` ticker. Test by searching a city far from your local timezone.

8. **`CurrencyCard.jsx`** — implement amount input, dropdowns, and the convert button. Verify that changing the city auto-selects the correct destination currency.

9. **`App.jsx` wiring** — connect all four cards, handle loading spinner and error states.

10. **Styling pass** — apply the dark card layout, CSS variables, responsive grid, emoji mapping, temperature color coding. Test on mobile viewport.

11. **Edge cases** — handle: unknown city name, MCP subprocess crash (auto-restart or graceful error), network timeouts, empty forecast array, unsupported currency codes.

12. **Final smoke test** — search Hanoi (VND home currency, same timezone as bridge server), Tokyo (UTC+9, JPY), Paris (UTC+2, EUR), New York (UTC-4, USD). Verify all four cards render correctly for each.

# Travel Dashboard (MCP)

A small full-stack lab that turns two Java MCP servers — [`utility-tools-mcp`](../utility-tools-mcp)
and [`flight-booking-mcp`](../flight-booking-mcp) — into a friendly travel dashboard. Type a city and
get its **current weather**, a **multi-day forecast**, the **local time**, and a **currency
converter** — plus an **AI concierge** that plans holiday trips *and books flights* for you.
Everything is powered by tool calls to the MCP servers over stdio.

```
                                  ┌─ GET /api/travel|currency|rate ─► parsed JSON for the cards
Browser (React/Vite) ──/api──►    │
        FastAPI backend           │                    ┌─ ask_travel_agent ─► utility-tools-mcp (Java)
        (2 MCP clients)           └─ POST /api/chat ─► orchestrator LLM ─┤
                                       (Gemini /                         └─ ask_flight_agent ─► flight-booking-mcp (Java)
                                        SiliconFlow)
                                                                          (each over stdio JSON-RPC)
```

The FastAPI backend hosts **two MCP clients** (one per Java jar). The dashboard endpoints parse the
utility server's tool output into clean JSON for the UI. The `/api/chat` endpoint runs an
**orchestrator LLM** that delegates to two specialist sub-agents — a **travel agent** (utility tools)
and a **flight agent** (flight-booking tools) — each of which calls its own MCP tools to reason toward
an answer; the orchestrator then synthesises one reply.

---

## Features

- 🔎 **City search** → geocode to lat/lon + IANA timezone
- 🌤️ **Current weather** (temperature, condition, humidity, wind)
- 📅 **5-day forecast** (min/max temp, condition, precipitation)
- 🕐 **Local time** at the destination, derived from its timezone
- 💱 **Currency converter** with live exchange rates; the destination's local currency is guessed
  from its timezone
- 🤖 **AI travel concierge** — an orchestrator that delegates to two specialist sub-agents: a
  **travel agent** (geocode, weather, forecast, attractions, holidays, currency) and a **flight
  agent** (search/book flights, look up bookings). It can use both in one message, and the chat
  shows a 🤝 **route badge** of which agent(s) handled each reply. Pick the LLM provider per message:
  **Gemini** or **SiliconFlow**.
- ✈️ **Flight booking** — search sample flights, book seats (get a `BK-` reference), and look up a
  booking, all in natural language via the flight agent.
- 🇻🇳 Vietnamese-language UI, dark theme, zero CSS framework (inline styles only)

All **travel data** comes from free, no-API-key public endpoints (Open-Meteo, ExchangeRate-API,
Wikipedia, Nager.Date) and the flight server ships with its own in-memory sample data, so the
dashboard runs out of the box. Only the **AI concierge** needs an LLM API key (Gemini and/or
SiliconFlow) — see [Configuration](#configuration).

---

## Project layout

```
travel-assistant/
├── backend/
│   ├── main.py            # FastAPI app: /api/travel, /api/currency, /api/rate, /api/chat, /health
│   ├── mcp_client.py      # stdio MCP client; two instances (utility_mcp, flight_mcp)
│   ├── llm.py             # provider primitives: schema translation + generic tool-calling loop
│   ├── agents.py          # SubAgent class + travel_agent & flight_agent (one MCP server each)
│   ├── orchestrator.py    # orchestrator LLM that delegates to the two sub-agents
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── api.js         # fetch wrappers for the /api endpoints
    │   └── components/    # CitySearch, WeatherCard, ForecastRow, ClockCard, CurrencyCard, ChatPanel
    ├── vite.config.js     # dev proxy /api → 127.0.0.1:8000
    └── package.json
```

---

## Prerequisites

- **Java 21+** and **Maven** — to build the two MCP server jars
- **Python 3.10+** — for the FastAPI bridge (uses `subprocess.Popen | None` syntax)
- **Node 18+** — for the Vite frontend
- **An LLM API key** (optional) — only for the AI assistant:
  [Gemini](https://aistudio.google.com/apikey) and/or
  [SiliconFlow](https://siliconflow.com). The dashboard works without one.

---

## Setup

### 1. Build the MCP servers (required first)

The bridge launches each Java jar as a subprocess, so **both** must exist before you start the
backend.

```bash
cd ../utility-tools-mcp
mvn clean package          # produces target/utility-tools-mcp-0.0.1.jar

cd ../flight-booking-mcp
mvn clean package          # produces target/flight-booking-mcp-0.0.1.jar
```

### 2. Start the backend (MCP client + REST bridge)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows;  on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # adjust the jar path if needed; add LLM key(s) to use the assistant

uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

To enable the AI assistant, set `GEMINI_API_KEY` and/or `SILICONFLOW_API_KEY` in `backend/.env`
(see [Configuration](#configuration)). Skip this if you only want the weather/currency dashboard.

On startup the `lifespan` handler spawns `java -jar <MCP_JAR_PATH>`, performs the MCP
`initialize` handshake, and keeps the process alive for the server's lifetime. Health check:
`GET http://127.0.0.1:8000/health`.

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Open <http://localhost:5173>, search for a city (e.g. `Tokyo`, `Hanoi`, `Paris`), and the
dashboard populates. The **AI assistant** panel sits at the bottom — pick a provider from the
dropdown and ask it to plan a trip (e.g. *"Gợi ý 3 điểm du lịch biển ấm áp tháng 12"*).

---

## Configuration

`backend/.env` (copied from `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `MCP_JAR_PATH` | `../../utility-tools-mcp/target/utility-tools-mcp-0.0.1.jar` | Path to the utility-tools jar |
| `FLIGHT_MCP_JAR_PATH` | `../../flight-booking-mcp/target/flight-booking-mcp-0.0.1.jar` | Path to the flight-booking jar |
| `BACKEND_HOST` | `0.0.0.0` | |
| `BACKEND_PORT` | `8000` | Must match the Vite proxy target |
| `GEMINI_API_KEY` | — | Required for the Gemini provider in `/api/chat` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model id |
| `SILICONFLOW_API_KEY` | — | Required for the SiliconFlow provider |
| `SILICONFLOW_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | SiliconFlow model id (must support tool calling) |
| `SILICONFLOW_BASE_URL` | `https://api.siliconflow.com/v1` | OpenAI-compatible endpoint |

> The AI assistant only needs the key(s) for the provider(s) you actually use. The weather/currency
> dashboard works without any LLM key.

---

## API

The backend exposes a thin REST layer. The frontend talks to it through the Vite dev proxy
(`/api/* → 127.0.0.1:8000`).

| Endpoint | Params | Returns |
|---|---|---|
| `GET /api/travel` | `city` | Geocode + weather + forecast + local time + guessed local currency |
| `GET /api/currency` | `from`, `to`, `amount` | Converted amount and rate |
| `GET /api/rate` | `from`, `to` | Latest exchange rate |
| `POST /api/chat` | body: `provider`, `messages[]`, `model?` | Concierge reply + agents + tools used |
| `GET /health` | — | `{"status": "ok"}` |

### `POST /api/chat`

```jsonc
// request
{ "provider": "gemini",          // or "siliconflow"
  "messages": [{ "role": "user", "content": "Tìm chuyến bay từ TP.HCM đi Hà Nội ngày mai" }],
  "model": null }                // optional override; falls back to the env default

// response
{ "reply": "…câu trả lời tiếng Việt…",
  "agents": ["flights"],          // which sub-agent(s) the orchestrator consulted
  "tool_calls": ["search_flights"],
  "provider": "gemini" }
```

The orchestrator runs a bounded tool-calling loop whose "tools" are the two sub-agents
(`ask_travel_agent`, `ask_flight_agent`). Each sub-agent in turn runs its own loop: tool schemas are
**discovered from its MCP server** via `tools/list` (no schemas are duplicated in Python), translated
into the provider's native tool format, and executed against that server as the model requests them.

`/api/travel` fans out to four MCP tools — `geocode` runs first, then `get_weather`,
`get_forecast`, and `current_time` run concurrently via `asyncio.gather`. Each response includes
a `raw` field with the original tool text for debugging.

### MCP tools used

The dashboard and the two sub-agents call these tools across the two servers:

| MCP tool | Server | Used for |
|---|---|---|
| `geocode` | utility | City name → lat/lon + timezone |
| `get_weather` | utility | Current conditions |
| `get_forecast` | utility | Daily forecast |
| `current_time` | utility | Local time at the destination |
| `convert_currency` / `get_exchange_rate` | utility | Currency card |
| `get_attractions` | utility | Nearby points of interest (travel agent) — Wikipedia GeoSearch, keyless |
| `get_public_holidays` | utility | Public holidays by country/year (travel agent) — Nager.Date, keyless |
| `search_flights` | flight | Find flights by route/date (flight agent) — in-memory sample data |
| `book_flight` | flight | Book seats, returns a `BK-` reference (flight agent) |
| `get_booking` | flight | Look up a booking by reference (flight agent) |

> `get_attractions` and `get_public_holidays` were added to `utility-tools-mcp` for this lab — rebuild
> the jar (`mvn clean package`) after pulling so the travel agent can use them.

---

## How the MCP bridge works

`mcp_client.py` is a minimal MCP client over **stdio**:

- It launches the jar with `subprocess.Popen` and exchanges newline-delimited JSON-RPC messages.
- I/O runs in a worker thread via `asyncio.to_thread`. This deliberately avoids asyncio's
  subprocess transport, which on Windows needs the `ProactorEventLoop` — unavailable under
  `uvicorn --reload` (which forces the `SelectorEventLoop`).
- The MCP handshake sends `initialize`, then the `notifications/initialized` notification; the
  server won't service `tools/call` until it receives that notification.
- Spring AI serializes a `String` tool result as a JSON string, so the text arrives
  double-encoded — the client unwraps it.

Because tool output is human-readable text (not structured JSON), `main.py` uses regex parsers
(`_parse_weather`, `_parse_forecast`, `_parse_time`, `_parse_currency`, etc.) to extract the
fields the UI needs.

---

## How the AI concierge works

The concierge is organised as an **orchestrator + two specialist sub-agents**, all sharing one
provider-agnostic tool-calling loop (`llm.py`).

- **Orchestrator (`orchestrator.py`).** An LLM whose two "tools" are the sub-agents —
  `ask_travel_agent` and `ask_flight_agent` (each takes a single `query` string). It reads the full
  conversation, delegates to the right specialist(s) — **calling both in one turn** for cross-domain
  requests — then synthesises one Vietnamese reply. The response reports which `agents` were consulted
  (used for the 🤝 route badge) and the underlying MCP `tool_calls`.
- **Sub-agents (`agents.py`).** Each `SubAgent` owns one MCP client. The **travel agent** uses a
  curated allowlist of the utility tools (`geocode`, `get_weather`, `get_forecast`, `current_time`,
  `convert_currency`, `get_exchange_rate`, `get_attractions`, `get_public_holidays`); the **flight
  agent** uses the flight server's tools (`search_flights`, `book_flight`, `get_booking`). Each
  discovers its tools from its own server via `tools/list` and runs the shared loop over the query the
  orchestrator handed it.
- **Tool discovery, not duplication.** Tool schemas live in the Java servers only and are translated
  into each provider's native format — OpenAI-style function specs for SiliconFlow,
  `types.FunctionDeclaration` for Gemini. A sanitizer strips keys Gemini rejects (`$schema`,
  `additionalProperties`).
- **Bounded loops.** Every loop (orchestrator and each sub-agent) is capped at 6 iterations to bound
  cost and latency; tool calls within a turn run concurrently via `asyncio.gather`.
- **Providers are selectable per request.** `provider: "gemini" | "siliconflow"`; each defaults to
  the model in `.env` but can be overridden with the `model` field. The orchestrator and sub-agents
  all use the same selected provider.

---

## Troubleshooting

- **`MCP jar not found`** on startup → build the server first (`mvn clean package`) or fix
  `MCP_JAR_PATH` in `.env`.
- **`MCP server closed the connection`** → the jar failed to start; check `mcp-server.log` in the
  server directory (the server logs to a file because stdout is the JSON-RPC channel).
- **Frontend can't reach the API / connection refused** → the Vite proxy targets `127.0.0.1`
  (not `localhost`) on purpose: on Windows `localhost` may resolve to IPv6 `::1` first, but
  uvicorn binds IPv4 `127.0.0.1`. Make sure the backend port matches the proxy target.
- **`City not found`** → geocoding returned no coordinates; try a more specific or differently
  spelled name.
- **Assistant returns `503 Assistant error: ... API key is not set`** → set `GEMINI_API_KEY` or
  `SILICONFLOW_API_KEY` in `backend/.env` for the provider you selected, then restart the backend.
- **Assistant ignores tools / gives generic answers** → use a model that supports function calling.
  The default `Qwen/Qwen2.5-7B-Instruct` works but is weaker at multi-step planning; bump the model
  via the `model` field or `SILICONFLOW_MODEL` / `GEMINI_MODEL`.
- **`get_attractions` returns `403 Forbidden`** → rebuild the jar; the Wikipedia client must send a
  `User-Agent` header (required by Wikipedia's API policy).

---

## Production build

```bash
cd frontend
npm run build        # emits frontend/dist/
```

Serve `dist/` behind any static host (or wire it into FastAPI), and point it at the running
backend.

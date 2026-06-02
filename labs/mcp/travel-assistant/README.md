# Travel Dashboard (MCP)

A small full-stack lab that turns the Java [`utility-tools-mcp`](../utility-tools-mcp) server
into a friendly travel dashboard. Type a city and get its **current weather**, a **multi-day
forecast**, the **local time**, and a **currency converter** — plus an **AI assistant** that plans
holiday trips for you. Everything is powered by tool calls to the MCP server over stdio.

```
                                  ┌─ GET /api/travel|currency|rate ─► parsed JSON for the cards
Browser (React/Vite) ──/api──►    │
        FastAPI backend           ├─ POST /api/chat ─► agent loop ─► Gemini / SiliconFlow (LLM)
        (MCP client)              │
                                  └──────── stdio JSON-RPC ────────► utility-tools-mcp (Java)
                                                                        │
                                              Open-Meteo · ExchangeRate-API · Wikipedia · Nager.Date · JDK
```

The FastAPI backend is an **MCP client**: it spawns the Java jar as a subprocess and speaks the
JSON-RPC MCP protocol to it. The dashboard endpoints parse the tool output into clean JSON for the
UI; the `/api/chat` endpoint hands the MCP tools to an LLM that calls them itself to reason toward
trip suggestions.

---

## Features

- 🔎 **City search** → geocode to lat/lon + IANA timezone
- 🌤️ **Current weather** (temperature, condition, humidity, wind)
- 📅 **5-day forecast** (min/max temp, condition, precipitation)
- 🕐 **Local time** at the destination, derived from its timezone
- 💱 **Currency converter** with live exchange rates; the destination's local currency is guessed
  from its timezone
- 🤖 **AI holiday-trip assistant** — a chat agent that calls the MCP tools itself (geocode, weather,
  forecast, attractions, holidays, currency) to suggest and plan trips. Pick the LLM provider per
  message: **Gemini** or **SiliconFlow**.
- 🇻🇳 Vietnamese-language UI, dark theme, zero CSS framework (inline styles only)

All **travel data** comes from free, no-API-key public endpoints (Open-Meteo, ExchangeRate-API,
Wikipedia, Nager.Date), so the dashboard runs out of the box. Only the **AI assistant** needs an
LLM API key (Gemini and/or SiliconFlow) — see [Configuration](#configuration).

---

## Project layout

```
utility-tools-mcp-travel-dashboard/
├── backend/
│   ├── main.py            # FastAPI app: /api/travel, /api/currency, /api/rate, /api/chat, /health
│   ├── mcp_client.py      # stdio MCP client (spawns the Java jar; call_tool + list_tools)
│   ├── agent.py           # provider-agnostic chat agent (Gemini + SiliconFlow tool-calling loop)
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

- **Java 21+** and **Maven** — to build the MCP server jar
- **Python 3.10+** — for the FastAPI bridge (uses `subprocess.Popen | None` syntax)
- **Node 18+** — for the Vite frontend
- **An LLM API key** (optional) — only for the AI assistant:
  [Gemini](https://aistudio.google.com/apikey) and/or
  [SiliconFlow](https://siliconflow.com). The dashboard works without one.

---

## Setup

### 1. Build the MCP server (required first)

The bridge launches the Java jar as a subprocess, so it must exist before you start the backend.

```bash
cd ../utility-tools-mcp
mvn clean package          # produces target/utility-tools-mcp-0.0.1.jar
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
| `MCP_JAR_PATH` | `../../utility-tools-mcp/target/utility-tools-mcp-0.0.1.jar` | Path to the built jar |
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
| `POST /api/chat` | body: `provider`, `messages[]`, `model?` | AI assistant reply + tools used |
| `GET /health` | — | `{"status": "ok"}` |

### `POST /api/chat`

```jsonc
// request
{ "provider": "gemini",          // or "siliconflow"
  "messages": [{ "role": "user", "content": "Gợi ý 3 điểm du lịch biển ấm tháng 12" }],
  "model": null }                // optional override; falls back to the env default

// response
{ "reply": "…câu trả lời tiếng Việt…",
  "tool_calls": ["geocode", "get_weather", "get_attractions"],
  "provider": "gemini" }
```

The backend runs a bounded tool-calling loop: tool schemas are **discovered from the MCP server**
via `tools/list` (no schemas are duplicated in Python), translated into each provider's native tool
format, and executed against the MCP server as the model requests them.

`/api/travel` fans out to four MCP tools — `geocode` runs first, then `get_weather`,
`get_forecast`, and `current_time` run concurrently via `asyncio.gather`. Each response includes
a `raw` field with the original tool text for debugging.

### MCP tools used

The dashboard and the AI assistant call these tools the server provides:

| MCP tool | Used for |
|---|---|
| `geocode` | City name → lat/lon + timezone |
| `get_weather` | Current conditions |
| `get_forecast` | Daily forecast |
| `current_time` | Local time at the destination |
| `convert_currency` / `get_exchange_rate` | Currency card |
| `get_attractions` | Nearby points of interest (assistant) — Wikipedia GeoSearch, keyless |
| `get_public_holidays` | Public holidays by country/year (assistant) — Nager.Date, keyless |

> `get_attractions` and `get_public_holidays` were added to `utility-tools-mcp` for this lab — rebuild
> the jar (`mvn clean package`) after pulling so the assistant can use them.

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

## How the AI assistant works

`agent.py` is a small, provider-agnostic agent loop:

- **Tool discovery, not duplication.** On first use it calls the MCP server's `tools/list`, filters
  to a curated travel-relevant allowlist (`geocode`, `get_weather`, `get_forecast`, `current_time`,
  `convert_currency`, `get_exchange_rate`, `get_attractions`, `get_public_holidays`), and caches
  the result. Tool schemas live in the Java server only.
- **Schema translation.** Each MCP JSON-Schema is translated into the provider's native tool format
  — OpenAI-style function specs for SiliconFlow, `types.FunctionDeclaration` for Gemini. A sanitizer
  strips keys Gemini rejects (`$schema`, `additionalProperties`).
- **Bounded tool-calling loop.** The model is asked the user's question with the tools attached;
  when it requests tool calls, the agent executes them against the MCP server (concurrently via
  `asyncio.gather`), feeds the results back, and repeats — capped at 6 iterations to bound cost and
  latency. The final text answer is returned (in Vietnamese), along with the list of tools used.
- **Providers are selectable per request.** `provider: "gemini" | "siliconflow"`; each defaults to
  the model in `.env` but can be overridden with the `model` field.

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

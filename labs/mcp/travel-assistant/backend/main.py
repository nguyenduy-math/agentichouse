import asyncio
import re
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import run_agent
from mcp_client import mcp

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mcp.start()
    yield
    await mcp.stop()


app = FastAPI(title="Travel Dashboard Bridge", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_geocode(text: str) -> dict:
    """Parse lat, lon, timezone from geocode result text."""
    lat = lon = timezone = None
    lat_m = re.search(r"latitude[\s:=]+(-?[\d.]+)", text, re.I)
    lon_m = re.search(r"longitude[\s:=]+(-?[\d.]+)", text, re.I)
    tz_m = re.search(r"timezone[\s:=]+([A-Za-z/_]+)", text, re.I)
    if lat_m:
        lat = float(lat_m.group(1))
    if lon_m:
        lon = float(lon_m.group(1))
    if tz_m:
        timezone = tz_m.group(1).strip()
    return {"lat": lat, "lon": lon, "timezone": timezone}


def _parse_weather(text: str) -> dict:
    """Parse current weather fields from text."""
    result = {
        "temperature": None,
        "condition": "",
        "humidity": None,
        "wind_speed": None,
        "wind_unit": "km/h",
    }
    temp_m = re.search(r"temperature[^:]*:\s*([-\d.]+)", text, re.I)
    if not temp_m:
        temp_m = re.search(r"([-\d.]+)\s*°?C", text)
    if temp_m:
        result["temperature"] = float(temp_m.group(1))

    cond_m = re.search(r"condition[^:]*:\s*([^\n,]+)", text, re.I)
    if cond_m:
        result["condition"] = cond_m.group(1).strip()
    else:
        # fallback: grab a descriptive phrase
        phrase_m = re.search(r"(Clear|Sunny|Cloudy|Rainy|Overcast|Drizzle|Thunder|Snow|Fog|Partly|Mainly|Light)[^\n,]*", text, re.I)
        if phrase_m:
            result["condition"] = phrase_m.group(0).strip()

    hum_m = re.search(r"humidity[^:]*:\s*([\d.]+)", text, re.I)
    if hum_m:
        result["humidity"] = float(hum_m.group(1))

    wind_m = re.search(r"wind[^:]*:\s*([\d.]+)", text, re.I)
    if wind_m:
        result["wind_speed"] = float(wind_m.group(1))

    return result


def _parse_forecast(text: str) -> list:
    """Parse up to 5 forecast days from text.

    Server format per line:
        - 2026-06-02: Thunderstorm, 27.9°C – 34.8°C, precip 0.3 mm
    (condition, then temp_min, then temp_max; separator is an en-dash or hyphen)
    """
    days = []
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2}):\s*([^,]+),\s*([-\d.]+)\s*°?C\s*[–\-]\s*([-\d.]+)\s*°?C"
        r"(?:[^\n]*?precip\s*([\d.]+))?",
        re.I,
    )
    for m in pattern.finditer(text):
        days.append({
            "date": m.group(1),
            "condition": m.group(2).strip(),
            "temp_min": float(m.group(3)),
            "temp_max": float(m.group(4)),
            "precipitation": float(m.group(5)) if m.group(5) else None,
        })
        if len(days) == 5:
            break

    return days


def _parse_time(text: str) -> dict:
    """Parse datetime and utc_offset from current_time result."""
    result = {"datetime": "", "timezone": "", "utc_offset_hours": 0}
    dt_m = re.search(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", text)
    if dt_m:
        result["datetime"] = dt_m.group(1)
    tz_m = re.search(r"timezone[=:\s]+([A-Za-z/_]+)", text, re.I)
    if tz_m:
        result["timezone"] = tz_m.group(1).strip()
    offset_m = re.search(r"UTC([+-]\d+)", text, re.I)
    if offset_m:
        result["utc_offset_hours"] = int(offset_m.group(1))
    else:
        # Try offset in hours from another pattern
        off2 = re.search(r"offset[^:]*:\s*([+-]?\d+)", text, re.I)
        if off2:
            result["utc_offset_hours"] = int(off2.group(1))
    return result


def _parse_currency(text: str) -> dict:
    result = {"converted": None, "rate": None}
    # convert_currency: "100.00 USD = 2,617,897.98 VND (rate 26178.979791, ...)"
    # get_exchange_rate: "1 USD = 26178.979791 VND (as of ...)"
    conv_m = re.search(r"=\s*([\d,. ]+?)\s*[A-Z]{3}", text)
    if conv_m:
        result["converted"] = float(conv_m.group(1).replace(",", "").replace(" ", ""))
    rate_m = re.search(r"rate[\s:=]+([\d,.]+)", text, re.I)
    if rate_m:
        result["rate"] = float(rate_m.group(1).replace(",", ""))
    elif re.match(r"\s*1\s+[A-Za-z]{3}\s*=", text):
        # The exchange-rate form has no "rate" keyword; the converted value is it.
        result["rate"] = result["converted"]
    return result


def _detect_currency(timezone: str) -> str:
    """Guess the local currency from the timezone string."""
    tz = (timezone or "").lower()
    mapping = {
        "asia/tokyo": "JPY", "asia/seoul": "KRW", "asia/shanghai": "CNY",
        "asia/hong_kong": "HKD", "asia/singapore": "SGD", "asia/bangkok": "THB",
        "asia/ho_chi_minh": "VND", "asia/saigon": "VND", "asia/hanoi": "VND",
        "asia/kolkata": "INR", "asia/dubai": "AED", "asia/riyadh": "SAR",
        "europe/london": "GBP", "europe/paris": "EUR", "europe/berlin": "EUR",
        "europe/rome": "EUR", "europe/madrid": "EUR", "europe/amsterdam": "EUR",
        "america/new_york": "USD", "america/los_angeles": "USD", "america/chicago": "USD",
        "america/toronto": "CAD", "america/vancouver": "CAD",
        "australia/sydney": "AUD", "australia/melbourne": "AUD",
    }
    for key, cur in mapping.items():
        if key in tz:
            return cur
    return "USD"


@app.get("/api/travel")
async def travel(city: str = Query(..., description="City name")):
    try:
        geo_text = await mcp.call_tool("geocode", {"place": city})
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MCP error: {e}")

    geo = _parse_geocode(geo_text)
    if not geo["lat"] or not geo["lon"]:
        raise HTTPException(status_code=400, detail=f"City not found: {city}")

    try:
        weather_text, forecast_text, time_text = await asyncio.gather(
            mcp.call_tool("get_weather", {"latitude": geo["lat"], "longitude": geo["lon"]}),
            mcp.call_tool("get_forecast", {"latitude": geo["lat"], "longitude": geo["lon"]}),
            mcp.call_tool("current_time", {"timezone": geo["timezone"] or "UTC"}),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MCP error: {e}")

    local_time = _parse_time(time_text)
    if geo["timezone"]:
        local_time["timezone"] = geo["timezone"]

    return {
        "city": city,
        "lat": geo["lat"],
        "lon": geo["lon"],
        "timezone": geo["timezone"],
        "local_currency": _detect_currency(geo["timezone"] or ""),
        "weather": _parse_weather(weather_text),
        "forecast": _parse_forecast(forecast_text),
        "local_time": local_time,
        "raw": {
            "geo": geo_text,
            "weather": weather_text,
            "forecast": forecast_text,
            "time": time_text,
        },
    }


@app.get("/api/currency")
async def currency(
    from_currency: str = Query(..., alias="from"),
    to_currency: str = Query(..., alias="to"),
    amount: float = Query(1.0),
):
    try:
        text = await mcp.call_tool("convert_currency", {
            "amount": amount,
            "from": from_currency,
            "to": to_currency,
        })
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MCP error: {e}")

    parsed = _parse_currency(text)
    return {
        "from": from_currency,
        "to": to_currency,
        "amount": amount,
        "converted": parsed["converted"],
        "rate": parsed["rate"],
        "raw": text,
    }


@app.get("/api/rate")
async def rate(
    from_currency: str = Query(..., alias="from"),
    to_currency: str = Query(..., alias="to"),
):
    try:
        text = await mcp.call_tool("get_exchange_rate", {
            "from": from_currency,
            "to": to_currency,
        })
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MCP error: {e}")

    parsed = _parse_currency(text)
    return {
        "from": from_currency,
        "to": to_currency,
        "rate": parsed["rate"],
        "raw": text,
    }


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    provider: str  # "gemini" | "siliconflow"
    messages: list[ChatMessage]
    model: str | None = None


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """AI holiday-trip assistant. Runs an MCP tool-calling loop on the chosen LLM."""
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    try:
        return await run_agent(req.provider, messages, req.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Assistant error: {e}")


@app.get("/health")
async def health():
    return {"status": "ok"}

import asyncio
import re
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

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
    lat_m = re.search(r"lat[=:\s]+(-?[\d.]+)", text, re.I)
    lon_m = re.search(r"lon[=:\s]+(-?[\d.]+)", text, re.I)
    tz_m = re.search(r"timezone[=:\s]+([A-Za-z/_]+)", text, re.I)
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
    """Parse up to 5 forecast days from text."""
    days = []
    # Match lines like: 2026-06-02: Sunny, max 25°C, min 18°C
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2})[^\n]*?(Clear|Sunny|Cloudy|Rainy|Overcast|Drizzle|Thunder|Snow|Fog|Partly|Mainly|Light)[^\n]*?"
        r"max[^:]*:\s*([-\d.]+)[^\n]*?min[^:]*:\s*([-\d.]+)",
        re.I,
    )
    for m in pattern.finditer(text):
        days.append({
            "date": m.group(1),
            "condition": m.group(2),
            "temp_max": float(m.group(3)),
            "temp_min": float(m.group(4)),
        })
        if len(days) == 5:
            break

    # Fallback: try simpler line-by-line parsing
    if not days:
        for line in text.splitlines():
            date_m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
            max_m = re.search(r"max[^:]*:\s*([-\d.]+)", line, re.I)
            min_m = re.search(r"min[^:]*:\s*([-\d.]+)", line, re.I)
            if date_m and max_m and min_m:
                days.append({
                    "date": date_m.group(1),
                    "condition": "Clear",
                    "temp_max": float(max_m.group(1)),
                    "temp_min": float(min_m.group(1)),
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
    # Match "100 USD = 2,540,000 VND" or "converted: 2540000"
    conv_m = re.search(r"=\s*([\d,. ]+)\s*[A-Z]{3}", text)
    if conv_m:
        result["converted"] = float(conv_m.group(1).replace(",", "").replace(" ", ""))
    rate_m = re.search(r"rate[^:]*:\s*([\d.]+)", text, re.I)
    if rate_m:
        result["rate"] = float(rate_m.group(1))
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
        geo_text = await mcp.call_tool("geocode", {"location": city})
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
            "from_currency": from_currency,
            "to_currency": to_currency,
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
            "from_currency": from_currency,
            "to_currency": to_currency,
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


@app.get("/health")
async def health():
    return {"status": "ok"}

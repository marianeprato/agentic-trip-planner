"""Weather forecast tool backed by Open-Meteo (free, keyless).

Open-Meteo's forecast endpoint only covers roughly the next 16 days. For a
date beyond that horizon, this falls back to a seasonal estimate built from
the same calendar week in last year's historical archive, rather than
failing outright -- useful for "what should I pack" advice on a trip
planned months out, at the cost of it being a typical-conditions estimate
rather than an actual forecast (see WeatherForecast.is_historical_estimate).
"""

from __future__ import annotations

from collections import Counter
from datetime import date as date_cls
from datetime import timedelta

import httpx
from agents import function_tool

from app.models import WeatherForecast
from app.tools._geocoding import geocode

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

_HISTORICAL_WINDOW_DAYS = 3

_WEATHER_CODE_DESCRIPTIONS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
}

_FORECAST_DAILY_FIELDS = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
# The archive/historical endpoint has no concept of "probability" (that's a
# forecast-model output) -- it silently returns null for
# precipitation_probability_max rather than erroring. precipitation_sum
# (actual measured mm) is the field that exists for historical data.
_ARCHIVE_DAILY_FIELDS = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"


def _safe_date(year: int, month: int, day: int) -> date_cls:
    """Handle Feb 29 in a non-leap reference year by falling back to Feb 28."""
    try:
        return date_cls(year, month, day)
    except ValueError:
        return date_cls(year, month, 28)


async def _fetch_daily(client: httpx.AsyncClient, url: str, fields: str, latitude: float, longitude: float, start: str, end: str) -> dict:
    response = await client.get(
        url,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": fields,
            "start_date": start,
            "end_date": end,
            "timezone": "auto",
        },
    )
    response.raise_for_status()
    return response.json().get("daily") or {}


async def _historical_estimate(destination: str, target: date_cls, latitude: float, longitude: float) -> WeatherForecast:
    reference_year = target.year - 1
    center = _safe_date(reference_year, target.month, target.day)
    start = center - timedelta(days=_HISTORICAL_WINDOW_DAYS)
    end = center + timedelta(days=_HISTORICAL_WINDOW_DAYS)

    async with httpx.AsyncClient(timeout=10.0) as client:
        daily = await _fetch_daily(client, ARCHIVE_URL, _ARCHIVE_DAILY_FIELDS, latitude, longitude, start.isoformat(), end.isoformat())

    if not daily or not daily.get("time"):
        raise ValueError(f"No historical data available for {destination} around {target.isoformat()}")

    # Open-Meteo's archive can return null for individual days with missing
    # station data -- drop those rather than letting sum() blow up on None.
    highs = [v for v in daily["temperature_2m_max"] if v is not None]
    lows = [v for v in daily["temperature_2m_min"] if v is not None]
    precip_sums = [v for v in daily["precipitation_sum"] if v is not None]
    codes = [v for v in daily["weather_code"] if v is not None]
    if not highs or not lows or not codes or not precip_sums:
        raise ValueError(f"No usable historical data available for {destination} around {target.isoformat()}")
    most_common_code = Counter(codes).most_common(1)[0][0]
    # No "probability" concept in historical data -- use the fraction of
    # reference days that saw measurable rain as a chance-of-rain proxy.
    rainy_day_pct = round(100 * sum(1 for v in precip_sums if v > 0) / len(precip_sums))

    return WeatherForecast(
        destination=destination,
        date=target.isoformat(),
        condition=_WEATHER_CODE_DESCRIPTIONS.get(most_common_code, f"code {most_common_code}"),
        temperature_high_c=round(sum(highs) / len(highs), 1),
        temperature_low_c=round(sum(lows) / len(lows), 1),
        precipitation_chance_pct=rainy_day_pct,
        is_historical_estimate=True,
    )


@function_tool
async def get_weather_forecast(destination: str, date: str) -> WeatherForecast:
    """Get the weather for a destination on a given date.

    If the date is too far out for a real forecast, returns a seasonal
    estimate from historical data instead (WeatherForecast.is_historical_estimate
    will be True) -- phrase advice accordingly rather than as a firm forecast.

    Args:
        destination: City or place name, e.g. "Lisbon" or "Tokyo, Japan".
        date: ISO date string (YYYY-MM-DD).
    """
    latitude, longitude = await geocode(destination)
    target = date_cls.fromisoformat(date)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            daily = await _fetch_daily(client, FORECAST_URL, _FORECAST_DAILY_FIELDS, latitude, longitude, date, date)
        if not daily or not daily.get("time"):
            raise ValueError("empty forecast response")
    except (httpx.HTTPStatusError, ValueError):
        return await _historical_estimate(destination, target, latitude, longitude)

    weather_code = daily["weather_code"][0]
    return WeatherForecast(
        destination=destination,
        date=date,
        condition=_WEATHER_CODE_DESCRIPTIONS.get(weather_code, f"code {weather_code}"),
        temperature_high_c=daily["temperature_2m_max"][0],
        temperature_low_c=daily["temperature_2m_min"][0],
        precipitation_chance_pct=daily["precipitation_probability_max"][0],
    )

"""Weather forecast tool backed by Open-Meteo (free, keyless)."""

from __future__ import annotations

import httpx
from agents import function_tool

from app.models import WeatherForecast

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

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


async def _geocode(destination: str) -> tuple[float, float]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(GEOCODING_URL, params={"name": destination, "count": 1})
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            raise ValueError(f"Could not geocode destination: {destination!r}")
        return results[0]["latitude"], results[0]["longitude"]


@function_tool
async def get_weather_forecast(destination: str, date: str) -> WeatherForecast:
    """Get the weather forecast for a destination on a given date.

    Args:
        destination: City or place name, e.g. "Lisbon" or "Tokyo, Japan".
        date: ISO date string (YYYY-MM-DD).
    """
    latitude, longitude = await _geocode(destination)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "start_date": date,
                "end_date": date,
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        daily = response.json().get("daily")
        if not daily or not daily.get("time"):
            raise ValueError(f"No forecast available for {destination} on {date}")

        weather_code = daily["weather_code"][0]
        return WeatherForecast(
            destination=destination,
            date=date,
            condition=_WEATHER_CODE_DESCRIPTIONS.get(weather_code, f"code {weather_code}"),
            temperature_high_c=daily["temperature_2m_max"][0],
            temperature_low_c=daily["temperature_2m_min"][0],
            precipitation_chance_pct=daily["precipitation_probability_max"][0],
        )

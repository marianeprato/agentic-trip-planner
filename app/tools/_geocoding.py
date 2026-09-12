"""Shared geocoding helpers. Not tools themselves -- no @function_tool
here, just plain functions the tools call internally.

Two different geocoders for two different jobs:
- geocode() (Open-Meteo, GeoNames-backed): good for city/place-level
  lookups like "Kyoto" or "Lisbon" -- what the weather tool needs.
- geocode_landmark() (Nominatim, OpenStreetMap-backed): resolves specific
  landmarks like "Kinkaku-ji, Kyoto" that GeoNames often doesn't know about
  -- needed by the restaurants tool, which also queries OSM's Overpass API
  for the actual results, so using OSM's own geocoder for the coordinates
  keeps both queries against the same underlying place database.
"""

from __future__ import annotations

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Nominatim's usage policy requires a descriptive User-Agent identifying the
# application, same requirement as Wikipedia's and Overpass's public APIs.
_NOMINATIM_HEADERS = {"User-Agent": "agentic-trip-planner/0.1 (learning project; https://github.com/marianeprato/agentic-trip-planner)"}


async def geocode(place: str) -> tuple[float, float]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(GEOCODING_URL, params={"name": place, "count": 1})
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            raise ValueError(f"Could not geocode place: {place!r}")
        return results[0]["latitude"], results[0]["longitude"]


async def geocode_landmark(place: str) -> tuple[float, float]:
    async with httpx.AsyncClient(timeout=10.0, headers=_NOMINATIM_HEADERS) as client:
        response = await client.get(NOMINATIM_URL, params={"q": place, "format": "json", "limit": 1})
        response.raise_for_status()
        results = response.json()
        if not results:
            raise ValueError(f"Could not geocode landmark: {place!r}")
        return float(results[0]["lat"]), float(results[0]["lon"])

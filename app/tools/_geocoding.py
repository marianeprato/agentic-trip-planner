"""Shared geocoding helpers. Not a tool itself -- no @function_tool here,
just a plain function the weather tool calls internally.
"""

from __future__ import annotations

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


async def geocode(place: str) -> tuple[float, float]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(GEOCODING_URL, params={"name": place, "count": 1})
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            raise ValueError(f"Could not geocode place: {place!r}")
        return results[0]["latitude"], results[0]["longitude"]

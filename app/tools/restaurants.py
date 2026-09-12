"""Nearby-restaurants tool backed by OpenStreetMap's Overpass API (free, keyless).

Returns real, named places rather than letting the model invent one --
naming a restaurant that doesn't exist is a worse failure than naming
nothing specific. Trade-off: OSM coverage/freshness varies by region, so
this is real data, not a live "open now" guarantee.
"""

from __future__ import annotations

import httpx
from agents import function_tool

from app.models import NearbyRestaurant
from app.tools._geocoding import geocode_landmark

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_SEARCH_RADIUS_M = 800
_MAX_RESULTS = 8

# Overpass's public instance rejects requests with a generic/default
# User-Agent, same issue as Wikipedia's API.
_HEADERS = {"User-Agent": "agentic-trip-planner/0.1 (learning project; https://github.com/marianeprato/agentic-trip-planner)"}

_QUERY_TEMPLATE = """
[out:json][timeout:25];
(
  node["amenity"="restaurant"](around:{radius},{lat},{lon});
  node["amenity"="cafe"](around:{radius},{lat},{lon});
);
out body {limit};
"""


def _format_address(tags: dict) -> str | None:
    street = tags.get("addr:street")
    number = tags.get("addr:housenumber")
    if street and number:
        return f"{number} {street}"
    return street


@function_tool
async def get_nearby_restaurants(place: str) -> list[NearbyRestaurant]:
    """Find real, named restaurants and cafes near a specific place.

    Args:
        place: A specific, geocodable place -- a landmark plus city works
            best, e.g. "Kinkaku-ji, Kyoto", not just the destination city.
    """
    latitude, longitude = await geocode_landmark(place)
    query = _QUERY_TEMPLATE.format(radius=_SEARCH_RADIUS_M, lat=latitude, lon=longitude, limit=_MAX_RESULTS * 3)

    async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
        response = await client.post(OVERPASS_URL, data={"data": query})
        response.raise_for_status()
        elements = response.json().get("elements", [])

    results = []
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        results.append(
            NearbyRestaurant(name=name, cuisine=tags.get("cuisine"), address=_format_address(tags))
        )
        if len(results) >= _MAX_RESULTS:
            break
    return results

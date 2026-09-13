"""Nearby-restaurants tool backed by OpenStreetMap's Overpass API (free, keyless).

Returns real, named places rather than letting the model invent one --
naming a restaurant that doesn't exist is a worse failure than naming
nothing specific. Trade-off: OSM coverage/freshness varies by region, so
this is real data, not a live "open now" guarantee.

The free public Overpass instances have no SLA and do occasionally time out
or 5xx under load (confirmed live -- see the trace attached to the task
this was written for). Retries each endpoint with backoff before moving to
the next public mirror, and only surfaces the tool-error (which the agent
is already instructed to handle gracefully) once every mirror has failed.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from agents import function_tool

from app.models import NearbyRestaurant
from app.tools._geocoding import geocode_landmark

logger = logging.getLogger(__name__)

# Tried in order; the second and third are independently-run public mirrors,
# not just DNS aliases of the first, so a primary outage doesn't take all
# three down at once.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
_RETRIES_PER_ENDPOINT = 2
_BACKOFF_BASE_SECONDS = 1.0
_SEARCH_RADIUS_M = 800
_MAX_RESULTS = 8

# Overpass's public instances reject requests with a generic/default
# User-Agent, same issue as Wikipedia's API.
_HEADERS = {"User-Agent": "agentic-trip-planner/0.1 (learning project; https://github.com/marianeprato/agentic-trip-planner)"}

_QUERY_TEMPLATE = """
[out:json][timeout:12];
(
  node["amenity"="restaurant"](around:{radius},{lat},{lon});
  node["amenity"="cafe"](around:{radius},{lat},{lon});
);
out body {limit};
"""


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, httpx.TimeoutException):
        return True
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500


async def _query_overpass(query: str) -> list[dict]:
    """Try each mirror in turn, retrying transient failures (timeouts, 5xx)
    with backoff before giving up on that mirror and moving to the next.
    Raises the last error only after every mirror is exhausted.
    """
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        for attempt in range(_RETRIES_PER_ENDPOINT):
            try:
                async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
                    response = await client.post(url, data={"data": query})
                    response.raise_for_status()
                    return response.json().get("elements", [])
            except (httpx.TimeoutException, httpx.HTTPStatusError) as error:
                last_error = error
                retryable = _is_retryable(error)
                is_last_attempt_on_endpoint = attempt == _RETRIES_PER_ENDPOINT - 1
                logger.warning("Overpass request to %s failed (attempt %d/%d): %s", url, attempt + 1, _RETRIES_PER_ENDPOINT, error)
                if retryable and not is_last_attempt_on_endpoint:
                    await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
                    continue
                break  # exhausted retries (or non-retryable) -- move to next mirror

    logger.warning("All Overpass mirrors failed for this query.")
    raise last_error if last_error is not None else RuntimeError("All Overpass endpoints failed")


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

    elements = await _query_overpass(query)

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

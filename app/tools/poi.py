"""Points-of-interest search tool backed by Wikipedia's GeoSearch API
(free, keyless) -- real, named places instead of a hardcoded dataset.

Geocodes the destination (reusing the same Open-Meteo geocoder the weather
tool uses), then asks Wikipedia for geotagged articles within its GeoData
extension's maximum radius (10km, not configurable) of that point, using
generator=geosearch + prop=extracts in one request so each result comes
back with a short description already attached.

Deliberately NOT ranked by popularity/notability. An earlier version tried
re-ranking by prop=pageviews, but live testing showed that prop silently
returns missing/zero data for a meaningful fraction of results when
combined with a generator -- confirmed live against pages with real,
substantial traffic (e.g. Nijo Castle) that came back as None. Rather than
ship a "popularity sort" that quietly lies for some results, this returns
Wikipedia's own distance-sorted order as-is and leaves picking the
genuinely interesting places to the calling agent's judgment (see
LOCAL_RECS_INSTRUCTIONS) -- the same trade-off already made everywhere
else in this project: real data over fabricated precision.

Known, accepted limitation: a 10km radius from the destination's
geocoded center can miss famous landmarks in geographically spread-out
cities (confirmed live for Kyoto -- Kinkaku-ji and Fushimi Inari Taisha
are both outside 10km of the city's administrative center point and never
appear). Accepted rather than worked around (e.g. multi-point searches)
to keep this a lightweight discovery tool, not a curated guide.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx
from agents import function_tool

from app.models import PointOfInterest
from app.tools._geocoding import geocode

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

# Wikipedia's API rejects requests with a generic/default User-Agent (403) --
# https://meta.wikimedia.org/wiki/User-Agent_policy requires a descriptive one.
_HEADERS = {"User-Agent": "agentic-trip-planner/0.1 (learning project; https://github.com/marianeprato/agentic-trip-planner)"}

_SEARCH_RADIUS_M = 10_000  # Wikipedia GeoData's maximum; not configurable higher.
_MAX_RESULTS = 8
_EXTRACT_CHARS = 280


@function_tool
async def search_points_of_interest(destination: str) -> list[PointOfInterest]:
    """Find real, named points of interest near a destination, sourced from Wikipedia.

    Results are sorted by distance from the destination's geocoded center,
    not by fame -- pick the genuinely interesting ones yourself rather than
    treating every result as a must-see attraction.

    Args:
        destination: City or place name, e.g. "Paris" or "Tokyo, Japan".
    """
    latitude, longitude = await geocode(destination)

    async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
        response = await client.get(
            WIKIPEDIA_API_URL,
            params={
                "action": "query",
                "generator": "geosearch",
                "ggscoord": f"{latitude}|{longitude}",
                "ggsradius": _SEARCH_RADIUS_M,
                "ggslimit": _MAX_RESULTS * 3,
                "prop": "extracts",
                "exintro": "true",
                "explaintext": "true",
                "exchars": _EXTRACT_CHARS,
                "format": "json",
                "formatversion": "2",
            },
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", [])

    destination_key = destination.strip().lower()
    results = []
    for page in pages:
        title = page.get("title", "")
        extract = page.get("extract")
        if not extract or title.strip().lower() == destination_key:
            continue
        results.append(
            PointOfInterest(
                name=title,
                description=extract,
                source_url=f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
            )
        )
        if len(results) >= _MAX_RESULTS:
            break
    return results

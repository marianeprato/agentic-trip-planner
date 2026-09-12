"""Place-facts tool backed by Wikipedia's search + REST summary APIs (free, keyless).

Grounds itinerary "fun facts" in a real reference rather than the model's
own training-data memory, which can be subtly wrong or out of date.

Resolves via Wikipedia's own search first rather than requiring an exact
page title: a query like "Kinkaku-ji, Kyoto" (a reasonable thing for the
model to pass, and the right form for the geocoding-based tools) is not a
valid page title and 404s against the summary endpoint directly, whereas
search correctly resolves it to the "Kinkaku-ji" page.
"""

from __future__ import annotations

import httpx
from agents import function_tool

from app.models import PlaceFacts

WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/rest.php/v1/search/page"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{key}"

# Wikipedia's API rejects requests with a generic/default User-Agent (403) --
# https://meta.wikimedia.org/wiki/User-Agent_policy requires a descriptive one.
_HEADERS = {"User-Agent": "agentic-trip-planner/0.1 (learning project; https://github.com/marianeprato/agentic-trip-planner)"}


@function_tool
async def get_place_facts(place: str) -> PlaceFacts:
    """Get a short, sourced summary fact about a specific place (e.g. a landmark,
    temple, or neighborhood) to weave into an itinerary.

    Args:
        place: The specific place name, e.g. "Kinkaku-ji" or "Eiffel Tower, Paris".
    """
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=_HEADERS) as client:
        search_response = await client.get(WIKIPEDIA_SEARCH_URL, params={"q": place, "limit": 1})
        search_response.raise_for_status()
        pages = search_response.json().get("pages") or []
        if not pages:
            raise ValueError(f"No Wikipedia page found for {place!r}")
        page_key = pages[0]["key"]

        summary_response = await client.get(WIKIPEDIA_SUMMARY_URL.format(key=page_key))
        summary_response.raise_for_status()
        data = summary_response.json()

    return PlaceFacts(
        place=data.get("title", place),
        extract=data.get("extract", ""),
        source_url=data.get("content_urls", {}).get("desktop", {}).get("page"),
    )

"""Unit tests for the four tools, called directly (not through an agent).

function_tool-wrapped functions expose the underlying callable via
`.on_invoke_tool`... but simpler: call `.on_invoke_tool` is JSON-string based.
Easiest path for direct unit testing is calling the original function through
`tool.function` when exposed, otherwise we call the plain module-level
coroutine before decoration is not available -- so instead we invoke the
FunctionTool via its public `on_invoke_tool(ctx, json_args)` and parse output.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
from agents.tool_context import ToolContext

from app.context import TripContext
from app.tools.budget import track_budget
from app.tools.currency import convert_currency
from app.tools.facts import get_place_facts
from app.tools.poi import search_points_of_interest
from app.tools.trip_details import update_trip_details
from app.tools.weather import get_weather_forecast


def _make_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=json_data, request=httpx.Request("GET", "https://example.com"))


async def _invoke(tool, context, **kwargs) -> dict:
    args_json = json.dumps(kwargs)
    ctx = ToolContext(context=context, tool_name=tool.name, tool_call_id="test-call", tool_arguments=args_json)
    raw = await tool.on_invoke_tool(ctx, args_json)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if isinstance(raw, list):
        return [item.model_dump() for item in raw]
    return raw.model_dump()


async def test_search_points_of_interest_returns_named_results_excluding_destination_page():
    geocode_response = _make_response({"results": [{"latitude": 35.02, "longitude": 135.75}]})
    geosearch_response = _make_response(
        {
            "query": {
                "pages": [
                    {"title": "Kyoto", "extract": "Kyoto is a city in Japan."},  # the destination itself -- excluded
                    {"title": "Nijō Castle", "extract": "A flatland castle in Kyoto."},
                    {"title": "Some Stub", "extract": ""},  # empty extract -- excluded
                    {"title": "Kyoto Imperial Palace"},  # no extract at all -- excluded
                ]
            }
        }
    )
    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=[geocode_response, geosearch_response])):
        result = await _invoke(search_points_of_interest, TripContext(), destination="Kyoto")

    assert len(result) == 1
    assert result[0]["name"] == "Nijō Castle"
    assert result[0]["description"] == "A flatland castle in Kyoto."
    assert result[0]["source_url"] == "https://en.wikipedia.org/wiki/Nij%C5%8D_Castle"


async def test_track_budget_accumulates_spend_in_context():
    context = TripContext(budget_amount=1000.0, budget_currency="USD")
    result = await _invoke(track_budget, context, item="Hotel", amount=300.0)
    assert result["spent"] == 300.0
    assert result["remaining"] == 700.0
    assert result["over_budget"] is False
    assert context.running_spent == 300.0

    result2 = await _invoke(track_budget, context, item="Flights", amount=800.0)
    assert result2["spent"] == 1100.0
    assert result2["over_budget"] is True
    assert len(context.spend_log) == 2


async def test_update_trip_details_only_overwrites_provided_fields():
    context = TripContext(destination="Rome")
    await _invoke(
        update_trip_details,
        context,
        destination=None,
        start_date="2027-06-01",
        end_date="2027-06-03",
        budget_amount=1000.0,
        budget_currency="gbp",
    )
    assert context.destination == "Rome"  # untouched, was not passed
    assert context.start_date.isoformat() == "2027-06-01"
    assert context.end_date.isoformat() == "2027-06-03"
    assert context.budget_amount == 1000.0
    assert context.budget_currency == "GBP"


async def test_update_trip_details_records_returning_visitor_and_preferences():
    context = TripContext()
    await _invoke(
        update_trip_details,
        context,
        is_returning_visitor=True,
        preferences=["Kinkaku-ji", "a sushi omakase dinner"],
    )
    assert context.is_returning_visitor is True
    assert context.preferences == ["Kinkaku-ji", "a sushi omakase dinner"]


async def test_update_trip_details_reports_no_change_for_repeated_identical_values():
    """Confirmed live: the routing agent can get stuck calling this
    repeatedly with unchanged values instead of progressing. Having the
    tool say so explicitly (rather than silently "succeeding" every time)
    gives the model something concrete to react to.
    """
    context = TripContext()

    first = await _invoke(update_trip_details, context, destination="Kyoto", budget_amount=100.0, budget_currency="GBP")
    assert first == "Trip details updated."  # still counts as new info the first time

    second = await _invoke(update_trip_details, context, destination="Kyoto", budget_amount=100.0, budget_currency="GBP")
    assert "nothing changed" in second.lower()


async def test_get_place_facts_resolves_via_search_then_fetches_summary(monkeypatch):
    search_response = _make_response({"pages": [{"key": "Kinkaku-ji", "title": "Kinkaku-ji"}]})
    summary_response = _make_response(
        {
            "title": "Kinkaku-ji",
            "extract": "A Zen Buddhist temple in Kyoto covered in gold leaf.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Kinkaku-ji"}},
        }
    )
    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=[search_response, summary_response])):
        result = await _invoke(get_place_facts, TripContext(), place="Kinkaku-ji, Kyoto")
    assert result["place"] == "Kinkaku-ji"
    assert "gold leaf" in result["extract"]
    assert result["source_url"] == "https://en.wikipedia.org/wiki/Kinkaku-ji"


async def test_convert_currency_same_currency_short_circuits():
    result = await _invoke(convert_currency, TripContext(), amount=100.0, from_currency="usd", to_currency="USD")
    assert result["converted_amount"] == 100.0
    assert result["rate"] == 1.0


async def test_convert_currency_calls_frankfurter_and_applies_rate():
    mock_response = _make_response({"amount": 1.0, "base": "USD", "date": "2026-01-01", "rates": {"EUR": 0.9}})
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        result = await _invoke(convert_currency, TripContext(), amount=100.0, from_currency="USD", to_currency="EUR")
    assert result["converted_amount"] == 90.0
    assert result["rate"] == 0.9


async def test_get_weather_forecast_geocodes_then_fetches_forecast():
    geocode_response = _make_response({"results": [{"latitude": 38.7, "longitude": -9.14}]})
    forecast_response = _make_response(
        {
            "daily": {
                "time": ["2027-06-01"],
                "weather_code": [1],
                "temperature_2m_max": [25.0],
                "temperature_2m_min": [16.0],
                "precipitation_probability_max": [10],
            }
        }
    )
    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=[geocode_response, forecast_response])):
        result = await _invoke(get_weather_forecast, TripContext(), destination="Lisbon", date="2027-06-01")

    assert result["condition"] == "mainly clear"
    assert result["temperature_high_c"] == 25.0
    assert result["precipitation_chance_pct"] == 10
    assert result["is_historical_estimate"] is False


async def test_get_weather_forecast_falls_back_to_historical_estimate_beyond_horizon():
    geocode_response = _make_response({"results": [{"latitude": 35.02, "longitude": 135.75}]})
    forecast_error_response = _make_response({"reason": "date too far out"}, status_code=400)
    archive_response = _make_response(
        {
            "daily": {
                "time": ["2025-10-19", "2025-10-20", "2025-10-21", "2025-10-22", "2025-10-23"],
                "weather_code": [1, 1, 2, 1, None],  # a day with missing station data
                "temperature_2m_max": [22.0, 23.0, 21.0, 24.0, None],
                "temperature_2m_min": [14.0, 15.0, 13.0, 16.0, None],
                "precipitation_sum": [0.0, 4.2, 0.0, 0.0, None],
            }
        }
    )

    def raise_for_status_error():
        raise httpx.HTTPStatusError("Bad Request", request=httpx.Request("GET", "https://x"), response=forecast_error_response)

    forecast_error_response.raise_for_status = raise_for_status_error

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(side_effect=[geocode_response, forecast_error_response, archive_response]),
    ):
        result = await _invoke(get_weather_forecast, TripContext(), destination="Kyoto", date="2026-10-22")

    assert result["is_historical_estimate"] is True
    assert result["temperature_high_c"] == 22.5  # None entry dropped before averaging
    assert result["condition"] == "mainly clear"
    assert result["precipitation_chance_pct"] == 25  # 1 of 4 usable reference days had rain

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
from app.tools.trip_details import update_trip_details
from app.tools.currency import convert_currency
from app.tools.poi import search_points_of_interest
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


async def test_search_points_of_interest_known_city_filters_by_category():
    result = await _invoke(search_points_of_interest, TripContext(), destination="Paris", category="museum")
    assert result
    assert all(poi["category"] == "museum" for poi in result)
    assert any(poi["name"] == "Louvre Museum" for poi in result)


async def test_search_points_of_interest_unknown_city_uses_generic_fallback():
    result = await _invoke(search_points_of_interest, TripContext(), destination="Nowheresville")
    assert len(result) == 4
    assert all("Nowheresville" in poi["name"] for poi in result)


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

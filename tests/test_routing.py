"""Tests for app/routing.py's structural pre-routing fix for the
post-itinerary Budget Agent handoff bug (see TESTING.md's known issues).
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from app.context import TripContext
from app.routing import is_explicit_budget_request


def _essentials_context() -> TripContext:
    from datetime import date

    return TripContext(
        destination="Paris",
        start_date=date(2027, 1, 1),
        end_date=date(2027, 1, 1),
        budget_amount=150.0,
        is_returning_visitor=False,
    )


async def test_short_circuits_false_when_essentials_are_missing():
    """No point classifying -- there's nothing to convert/track yet, and
    the handoff itself is structurally disabled until essentials are
    gathered (see app/agents/__init__.py's is_enabled=). Also confirms no
    model call is made in this case."""
    with patch("app.routing.Runner.run", new=AsyncMock()) as mock_run:
        result = await is_explicit_budget_request("Can you convert 150 GBP to EUR?", TripContext())

    assert result is False
    mock_run.assert_not_called()


async def test_returns_classifier_result_once_essentials_are_gathered():
    @dataclass
    class _FakeOutput:
        is_explicit_currency_or_expense_request: bool

    @dataclass
    class _FakeResult:
        final_output: _FakeOutput

    with patch("app.routing.Runner.run", new=AsyncMock(return_value=_FakeResult(_FakeOutput(True)))):
        result = await is_explicit_budget_request("Can you convert 150 GBP to EUR?", _essentials_context())

    assert result is True


async def test_returns_false_when_classifier_says_no():
    @dataclass
    class _FakeOutput:
        is_explicit_currency_or_expense_request: bool

    @dataclass
    class _FakeResult:
        final_output: _FakeOutput

    with patch("app.routing.Runner.run", new=AsyncMock(return_value=_FakeResult(_FakeOutput(False)))):
        result = await is_explicit_budget_request("What's the weather like?", _essentials_context())

    assert result is False

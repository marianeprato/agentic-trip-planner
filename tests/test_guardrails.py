"""Guardrails are just functions returning GuardrailFunctionOutput, so they're
testable directly -- no agent run required except for the LLM-backed
semantic check, which uses a ScriptedModel (no live API key needed).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from agents import RunContextWrapper
from agents.testing import ScriptedModel, assistant_message

import app.guardrails.input_guardrails as input_guardrails_module
from app.context import TripContext
from app.guardrails.input_guardrails import validate_trip_request
from app.guardrails.output_guardrails import validate_budget_compliance
from app.models import ItineraryDay, ItineraryOutput, PlannerResponse

_TODAY = date.today()


async def test_input_guardrail_flags_end_date_before_start_date():
    start = _TODAY + timedelta(days=10)
    end = _TODAY + timedelta(days=5)
    text = f"Plan a trip to Rome from {start.isoformat()} to {end.isoformat()}."

    result = await validate_trip_request.guardrail_function(None, None, text)

    assert result.tripwire_triggered is True


async def test_input_guardrail_flags_start_date_in_the_past():
    start = _TODAY - timedelta(days=5)
    end = _TODAY + timedelta(days=5)
    text = f"Plan a trip to Rome from {start.isoformat()} to {end.isoformat()}."

    result = await validate_trip_request.guardrail_function(None, None, text)

    assert result.tripwire_triggered is True


async def test_input_guardrail_allows_sensible_dates_and_valid_destination(monkeypatch):
    # Sensible dates only skip the *tripwire*, not the LLM destination check --
    # that still runs on every call, so it needs mocking here too.
    scripted_model = ScriptedModel(
        [[assistant_message(json.dumps({"is_valid": True, "reasoning": "Rome is a real city."}))]]
    )
    test_validator = input_guardrails_module.trip_request_validator_agent.clone(model=scripted_model)
    monkeypatch.setattr(input_guardrails_module, "trip_request_validator_agent", test_validator)

    start = _TODAY + timedelta(days=10)
    end = _TODAY + timedelta(days=15)
    text = f"Plan a trip to Rome from {start.isoformat()} to {end.isoformat()}."

    result = await validate_trip_request.guardrail_function(None, None, text)

    assert result.tripwire_triggered is False


async def test_input_guardrail_llm_check_flags_nonsense_destination(monkeypatch):
    scripted_model = ScriptedModel(
        [[assistant_message(json.dumps({"is_valid": False, "reasoning": "Narnia is fictional."}))]]
    )
    test_validator = input_guardrails_module.trip_request_validator_agent.clone(model=scripted_model)
    monkeypatch.setattr(input_guardrails_module, "trip_request_validator_agent", test_validator)

    result = await validate_trip_request.guardrail_function(None, None, "I want to plan a trip to Narnia.")

    assert result.tripwire_triggered is True


def _sample_itinerary(total_cost: float) -> PlannerResponse:
    return PlannerResponse(
        status="itinerary",
        itinerary=ItineraryOutput(
            destination="Lisbon",
            start_date="2027-01-01",
            end_date="2027-01-03",
            currency="USD",
            days=[ItineraryDay(date="2027-01-01", summary="Arrival", activities=["Check in"], estimated_cost=total_cost)],
            total_estimated_cost=total_cost,
            budget_amount=1000.0,
        ),
    )


async def test_output_guardrail_allows_within_budget_itinerary():
    ctx = RunContextWrapper(context=TripContext(budget_amount=1000.0))
    output = _sample_itinerary(total_cost=900.0)

    result = await validate_budget_compliance.guardrail_function(ctx, None, output)

    assert result.tripwire_triggered is False


async def test_output_guardrail_flags_itinerary_over_budget_tolerance():
    ctx = RunContextWrapper(context=TripContext(budget_amount=1000.0))
    output = _sample_itinerary(total_cost=1200.0)  # > 5% tolerance over 1000

    result = await validate_budget_compliance.guardrail_function(ctx, None, output)

    assert result.tripwire_triggered is True


async def test_output_guardrail_ignores_clarifying_question_turns():
    ctx = RunContextWrapper(context=TripContext(budget_amount=1000.0))
    output = PlannerResponse(status="clarifying_question", message="What's your budget?")

    result = await validate_budget_compliance.guardrail_function(ctx, None, output)

    assert result.tripwire_triggered is False

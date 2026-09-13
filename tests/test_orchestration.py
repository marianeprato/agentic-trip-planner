"""Tests for app/orchestration.py's bounded-failure handling: the
guardrail-revision loop (task 2/3) and the bounded-turns fallback (task 3),
using ScriptedModel so no live API key is needed.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock

from agents import handoff
from agents.testing import ScriptedModel, assistant_message, function_call

import app.orchestration as orchestration_module
from app.agents.budget_agent import budget_agent
from app.agents.itinerary_composer_agent import itinerary_composer_agent
from app.agents.triage_agent import triage_agent
from app.context import TripContext
from app.orchestration import MAX_GUARDRAIL_REVISIONS, run_turn


def _itinerary_step(total_cost: float):
    payload = {
        "status": "itinerary",
        "message": None,
        "itinerary": {
            "destination": "Lisbon",
            "start_date": "2027-01-01",
            "end_date": "2027-01-01",
            "currency": "GBP",
            "days": [
                {
                    "date": "2027-01-01",
                    "summary": "A day in Lisbon",
                    "activities": [{"time": "3:00 PM", "description": "Check in", "fun_fact": None}],
                    "estimated_cost": total_cost,
                }
            ],
            "total_estimated_cost": total_cost,
            "budget_amount": 100.0,
            "within_budget": total_cost <= 100.0,
        },
    }
    return [assistant_message(json.dumps(payload))]


def _wire_test_agents(monkeypatch, scripted_model):
    """Clones Triage + Composer onto one ScriptedModel and points
    app.orchestration at the clones instead of the real singletons."""
    test_triage = triage_agent.clone(model=scripted_model, handoffs=[], input_guardrails=[])
    test_composer = itinerary_composer_agent.clone(model=scripted_model, handoffs=[handoff(test_triage)])
    test_triage.handoffs = [handoff(test_composer)]
    monkeypatch.setattr(orchestration_module, "triage_agent", test_triage)
    return test_triage, test_composer


async def test_revision_succeeds_within_budget_on_retry(monkeypatch):
    scripted_model = ScriptedModel()
    test_triage, test_composer = _wire_test_agents(monkeypatch, scripted_model)
    triage_to_composer = handoff(test_composer).tool_name

    scripted_model.extend(
        [
            # Attempt 1: hands off, composer proposes something over budget.
            [function_call(name=triage_to_composer, arguments={}, call_id="call_1")],
            _itinerary_step(total_cost=500.0),
            # Attempt 2 (after the revision nudge): hands off again, this
            # time within budget.
            [function_call(name=triage_to_composer, arguments={}, call_id="call_2")],
            _itinerary_step(total_cost=90.0),
        ]
    )

    context = TripContext(destination="Lisbon", budget_amount=100.0, budget_currency="GBP")
    result = await run_turn("Plan my trip.", session=None, context=context)

    assert result.output.status == "itinerary"
    assert result.output.itinerary.total_estimated_cost == 90.0
    assert result.last_agent_name == "Itinerary Composer Agent"


async def test_revision_gives_up_after_max_attempts_with_clear_fallback(monkeypatch):
    scripted_model = ScriptedModel()
    test_triage, test_composer = _wire_test_agents(monkeypatch, scripted_model)
    triage_to_composer = handoff(test_composer).tool_name

    # One initial attempt + MAX_GUARDRAIL_REVISIONS retries, all over budget.
    steps = []
    for i in range(MAX_GUARDRAIL_REVISIONS + 1):
        steps.append([function_call(name=triage_to_composer, arguments={}, call_id=f"call_{i}")])
        steps.append(_itinerary_step(total_cost=500.0))
    scripted_model.extend(steps)

    context = TripContext(destination="Lisbon", budget_amount=100.0, budget_currency="GBP")
    result = await run_turn("Plan my trip.", session=None, context=context)

    assert result.output.status == "clarifying_question"
    assert "budget" in result.output.message.lower()
    assert result.last_agent_name == "Itinerary Composer Agent"
    # Confirms it actually stopped instead of retrying forever: exactly
    # MAX_GUARDRAIL_REVISIONS + 1 attempts worth of steps were consumed, no more.
    assert scripted_model.remaining_steps == 0


async def test_bounded_turns_falls_back_instead_of_looping_indefinitely(monkeypatch):
    monkeypatch.setattr(orchestration_module, "MAX_TURNS", 2)

    scripted_model = ScriptedModel()
    test_triage, test_composer = _wire_test_agents(monkeypatch, scripted_model)
    triage_to_composer = handoff(test_composer).tool_name
    composer_to_triage = handoff(test_triage).tool_name

    # A pathological back-and-forth: Triage -> Composer -> Triage, never
    # reaching a final output. With MAX_TURNS=2 this must be cut off rather
    # than looping (in production, further) indefinitely.
    scripted_model.extend(
        [
            [function_call(name=triage_to_composer, arguments={}, call_id="call_1")],
            [function_call(name=composer_to_triage, arguments={}, call_id="call_2")],
        ]
    )

    context = TripContext(destination="Lisbon", budget_amount=100.0, budget_currency="GBP")
    result = await run_turn("Plan my trip.", session=None, context=context)

    assert result.output.status == "clarifying_question"
    assert "back-and-forth" in result.output.message.lower() or "simplify" in result.output.message.lower()


async def test_explicit_budget_request_starts_from_budget_agent_not_triage(monkeypatch):
    """Structural fix for the post-itinerary Budget Agent routing bug (see
    app/routing.py): when is_explicit_budget_request is True, the turn
    starts from budget_agent_direct -- a Budget Agent variant with no
    handoff back to Triage -- rather than Triage's own unreliable routing
    decision. No handoff back is deliberate: live testing showed that
    letting Budget hand back to Triage as normal reintroduces the same
    failure through a different door (Triage re-reads the same original
    message and hands off to Budget again, sometimes bouncing repeatedly).
    """
    scripted_model = ScriptedModel()
    test_triage = triage_agent.clone(model=scripted_model, handoffs=[], input_guardrails=[])
    test_budget_direct = budget_agent.clone(model=scripted_model, handoffs=[])
    monkeypatch.setattr(orchestration_module, "triage_agent", test_triage)
    monkeypatch.setattr(orchestration_module, "budget_agent_direct", test_budget_direct)
    monkeypatch.setattr(orchestration_module, "is_explicit_budget_request", AsyncMock(return_value=True))

    final_payload = {"status": "clarifying_question", "message": "That's 175.50 EUR."}
    scripted_model.extend(
        [
            # A single step, no handoff call at all -- if Triage's own
            # (unmocked) routing judgment were used instead, this scripted
            # step wouldn't match what the model is actually asked to do.
            [assistant_message(json.dumps(final_payload))],
        ]
    )

    context = TripContext(
        destination="Paris",
        start_date=date(2027, 1, 1),
        end_date=date(2027, 1, 1),
        budget_amount=150.0,
        is_returning_visitor=False,
    )
    result = await run_turn("Can you convert 150 GBP to EUR?", session=None, context=context)

    assert result.output.message == "That's 175.50 EUR."
    assert result.last_agent_name == "Budget Agent"
    assert scripted_model.remaining_steps == 0

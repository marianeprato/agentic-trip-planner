"""Verifies the star handoff topology actually routes control, using the
SDK's ScriptedModel test double -- no live OpenAI calls, no API key needed.

Guardrails are stripped from the cloned Triage agent here: this test is
scoped to handoff *routing* (does a budget-flavored turn actually reach the
Budget agent, and does control return to Triage for the final output), which
is a separate concern from guardrail behavior already covered in
test_guardrails.py.
"""

from __future__ import annotations

import json

import pytest
from agents import OutputGuardrailTripwireTriggered, Runner, handoff
from agents.testing import ScriptedModel, assistant_message, function_call

from app.agents.budget_agent import budget_agent
from app.agents.itinerary_composer_agent import itinerary_composer_agent
from app.agents.triage_agent import triage_agent
from app.context import TripContext
from app.models import PlannerResponse


async def test_handoff_to_budget_agent_and_back_to_triage():
    scripted_model = ScriptedModel()

    test_triage = triage_agent.clone(model=scripted_model, handoffs=[], input_guardrails=[], output_guardrails=[])
    test_budget = budget_agent.clone(model=scripted_model, handoffs=[handoff(test_triage)])
    test_triage.handoffs = [handoff(test_budget)]

    triage_to_budget = handoff(test_budget).tool_name
    budget_to_triage = handoff(test_triage).tool_name

    scripted_model.extend(
        [
            # 1. Triage decides this needs the Budget Agent.
            [function_call(name=triage_to_budget, arguments={}, call_id="call_1")],
            # 2. Budget Agent calls track_budget directly (context already in USD).
            [function_call(name="track_budget", arguments={"item": "Hotel", "amount": 200}, call_id="call_2")],
            # 3. Budget Agent hands back to Triage.
            [function_call(name=budget_to_triage, arguments={}, call_id="call_3")],
            # 4. Triage composes the final structured response.
            [
                assistant_message(
                    json.dumps(
                        {
                            "status": "clarifying_question",
                            "message": "Got it, logged $200 for the hotel. What else can I help with?",
                            "itinerary": None,
                        }
                    )
                )
            ],
        ]
    )

    context = TripContext(destination="Lisbon", budget_amount=1000.0, budget_currency="USD")
    result = await Runner.run(test_triage, "Track $200 for my hotel.", context=context)

    assert result.last_agent.name == "Triage Agent"
    assert isinstance(result.final_output, PlannerResponse)
    assert result.final_output.status == "clarifying_question"
    assert context.running_spent == 200

    handoff_item_names = [
        item.__class__.__name__ for item in result.new_items if item.__class__.__name__ == "HandoffOutputItem"
    ]
    assert len(handoff_item_names) == 2, "expected one handoff out to Budget and one back to Triage"


def _itinerary_payload(total_cost: float) -> dict:
    return {
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
                    "summary": "Arrival",
                    "activities": [{"time": "3:00 PM", "description": "Check in", "fun_fact": None}],
                    "estimated_cost": total_cost,
                }
            ],
            "total_estimated_cost": total_cost,
            "budget_amount": 100.0,
            "within_budget": True,
        },
    }


async def test_triage_hands_off_to_composer_which_produces_the_itinerary():
    scripted_model = ScriptedModel()

    test_triage = triage_agent.clone(model=scripted_model, handoffs=[], input_guardrails=[])
    test_composer = itinerary_composer_agent.clone(model=scripted_model, handoffs=[handoff(test_triage)])
    test_triage.handoffs = [handoff(test_composer)]

    triage_to_composer = handoff(test_composer).tool_name

    scripted_model.extend(
        [
            [function_call(name=triage_to_composer, arguments={}, call_id="call_1")],
            [assistant_message(json.dumps(_itinerary_payload(total_cost=90.0)))],
        ]
    )

    context = TripContext(destination="Lisbon", budget_amount=100.0, budget_currency="GBP")
    result = await Runner.run(test_triage, "Plan my trip.", context=context)

    assert result.last_agent.name == "Itinerary Composer Agent"
    assert result.final_output.status == "itinerary"
    assert result.final_output.itinerary.total_estimated_cost == 90.0


async def test_composer_output_guardrail_still_fires_after_the_split():
    """validate_budget_compliance moved from Triage to Composer when Triage
    became a pure router -- confirm it's still actually wired, not just
    present in test_guardrails.py's direct (agent-less) checks.
    """
    scripted_model = ScriptedModel([[assistant_message(json.dumps(_itinerary_payload(total_cost=500.0)))]])
    test_composer = itinerary_composer_agent.clone(model=scripted_model, handoffs=[])

    context = TripContext(destination="Lisbon", budget_amount=100.0, budget_currency="GBP")

    with pytest.raises(OutputGuardrailTripwireTriggered):
        await Runner.run(test_composer, "Write the itinerary.", context=context)

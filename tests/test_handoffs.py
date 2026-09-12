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

from agents import Runner, handoff
from agents.testing import ScriptedModel, assistant_message, function_call

from app.agents.budget_agent import budget_agent
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

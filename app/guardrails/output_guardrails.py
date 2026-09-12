"""Output guardrail: validate_budget_compliance.

Pure arithmetic against the produced ItineraryOutput and the shared
TripContext -- no LLM call needed, deliberately contrasted with the
LLM-backed input guardrail. Attached only to the Triage agent, since it's
the only agent whose output is ever returned as a final ItineraryOutput
(see build-order flag #2 in the plan for why every run always starts at,
and finishes through, Triage).
"""

from __future__ import annotations

from agents import Agent, GuardrailFunctionOutput, RunContextWrapper, output_guardrail

from app.context import TripContext
from app.models import PlannerResponse

_TOLERANCE_PCT = 0.05


@output_guardrail
async def validate_budget_compliance(
    ctx: RunContextWrapper[TripContext], agent: Agent, agent_output: PlannerResponse
) -> GuardrailFunctionOutput:
    if agent_output.status != "itinerary" or agent_output.itinerary is None:
        return GuardrailFunctionOutput(
            output_info={"reason": "Not a final itinerary this turn; nothing to check."},
            tripwire_triggered=False,
        )

    budget = ctx.context.budget_amount
    if budget is None:
        return GuardrailFunctionOutput(output_info={"reason": "No budget set; nothing to check."}, tripwire_triggered=False)

    itinerary = agent_output.itinerary
    total = itinerary.total_estimated_cost
    allowed = budget * (1 + _TOLERANCE_PCT)
    over_budget = total > allowed

    return GuardrailFunctionOutput(
        output_info={
            "total_estimated_cost": total,
            "budget_amount": budget,
            "tolerance_pct": _TOLERANCE_PCT,
            "reason": (
                f"Itinerary total {total} {itinerary.currency} exceeds budget "
                f"{budget} {itinerary.currency} beyond the {_TOLERANCE_PCT:.0%} tolerance."
                if over_budget
                else "Within budget."
            ),
        },
        tripwire_triggered=over_budget,
    )

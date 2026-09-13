"""Deterministic pre-routing for a case Triage's own judgment doesn't
reliably handle: an explicit currency-conversion/expense-tracking request
made after an itinerary already exists in the conversation.

Confirmed live: Triage's tool_choice="required" only binds the *first*
model call of a Runner.run (the SDK's reset_tool_choice defaults to True,
reverting to "auto" after any tool call within that same run). By the time
a follow-up like "convert 150 GBP to EUR" arrives, the conversation
history already contains a full itinerary -- Triage's forced first tool
call is often a no-op update_trip_details, and once tool_choice reverts to
"auto" the cheap routing model sometimes just re-emits the existing
itinerary instead of reconsidering the new message and handing off. Three
rounds of tightening TRIAGE_INSTRUCTIONS narrowed but did not eliminate
this (see TESTING.md's known issues). Rather than a fourth wording
attempt, this runs a tiny, cheap classifier before Triage and -- only once
TripContext.has_all_essentials() is true, the same structural gate already
used for the handoffs themselves (see app/agents/__init__.py's is_enabled=)
-- starts that turn's Runner.run directly from a Budget Agent variant that
answers the user itself, bypassing Triage's unreliable decision entirely.

That variant (budget_agent_direct) has no handoff back to Triage, unlike
the normal budget_agent used everywhere else in the handoff graph. This is
deliberate, not an oversight: letting Budget hand back to Triage as usual
was tried first and confirmed live to reintroduce the same failure through
a different door -- Triage, regaining control with the original ("convert
150 GBP...") message still the most recent user turn in history, re-reads
its own routing rules against that unchanged message and hands off to
Budget *again*, sometimes bouncing 2-3 times before either recovering or
(confirmed live) losing track of TripContext entirely and asking the user
for destination/dates/budget again from scratch. Removing the handoff tool
structurally forces Budget to answer directly instead -- its
SpokeFallbackResponse.message field already carries the actual result
fine (confirmed live: "150 GBP converts to approximately 174.79 EUR...").

A false positive on the classifier is cheap, not wrong: budget_agent_direct
still has no specific expense/conversion to act on in that case, so its
reply just says as much rather than fabricating one -- one wrong turn's
wording, not an incorrect handoff or lost context.
"""

from __future__ import annotations

from agents import Agent, Runner
from pydantic import BaseModel

from app.agents.budget_agent import budget_agent
from app.config import OPENAI_ROUTING_MODEL
from app.context import TripContext

# See module docstring for why this has no handoff back to Triage, unlike
# the budget_agent used everywhere else in the normal handoff graph.
budget_agent_direct = budget_agent.clone(handoffs=[])


class _BudgetIntentClassification(BaseModel):
    is_explicit_currency_or_expense_request: bool


_CLASSIFIER_INSTRUCTIONS = """
Decide whether the user's message explicitly asks for currency conversion
or expense tracking -- e.g. "convert 150 GBP to EUR", "how much is my
budget in USD", "log 40 EUR for lunch". Answer true only for an explicit
ask like these.

Answer false for everything else, including a message that simply states
a budget amount as part of describing a trip, asks about or repeats an
itinerary, or asks for local recommendations.
""".strip()

# No output_guardrails/handoffs needed -- this agent is only ever invoked
# standalone via Runner.run, never reached through the handoff graph.
_budget_intent_classifier_agent = Agent(
    name="Budget Intent Classifier",
    instructions=_CLASSIFIER_INSTRUCTIONS,
    model=OPENAI_ROUTING_MODEL,
    output_type=_BudgetIntentClassification,
)


async def is_explicit_budget_request(user_input: str, context: TripContext) -> bool:
    """True only once essentials are gathered (mirrors the structural
    handoff gate -- there's nothing to convert/track before then anyway)
    and the classifier confirms this specific message is an explicit
    currency/expense ask. Deliberately classifies user_input alone, not
    the full session history -- this is "is *this* message an explicit
    ask," not a judgment that needs prior context.
    """
    if not context.has_all_essentials():
        return False
    result = await Runner.run(_budget_intent_classifier_agent, user_input)
    return result.final_output.is_explicit_currency_or_expense_request

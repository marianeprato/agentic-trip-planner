"""Triage Agent: entry point for every Runner.run() call, and the only
router in the graph -- it never writes the itinerary itself (that's the
Itinerary Composer Agent's job, on the stronger model).

Handoffs are wired in app/agents/__init__.py (not here) to avoid a circular
import -- Budget, Local Recs, and Composer each need a handoff *back* to
this agent, so this module must not import them.

Runs on OPENAI_ROUTING_MODEL (cheap/fast): deciding what to ask next or
which specialist to hand off to is a classification-shaped task, not
generation -- see README's "Cost-aware model routing" section.

tool_choice="required" forces the *first* turn of every run to be a tool
call (reset_tool_choice, the SDK default, reverts to "auto" after any tool
call, so this doesn't force every turn). Confirmed live this is needed:
without it, the cheap routing model would sometimes skip calling
update_trip_details entirely and jump straight to asking about the one
still-missing field, silently never recording the destination/dates/budget
the user had just given it in the same message.
"""

from agents import Agent, ModelSettings

from app.agents.prompts import TRIAGE_INSTRUCTIONS
from app.config import OPENAI_ROUTING_MODEL
from app.context import TripContext
from app.guardrails.input_guardrails import validate_trip_request
from app.models import PlannerResponse
from app.tools.trip_details import update_trip_details

triage_agent = Agent[TripContext](
    name="Triage Agent",
    instructions=TRIAGE_INSTRUCTIONS,
    model=OPENAI_ROUTING_MODEL,
    model_settings=ModelSettings(tool_choice="required"),
    tools=[update_trip_details],
    handoffs=[],  # populated in app/agents/__init__.py
    output_type=PlannerResponse,
    input_guardrails=[validate_trip_request],
    # No output_guardrails here: Triage never emits status="itinerary" (only
    # the Itinerary Composer Agent does), so validate_budget_compliance
    # belongs there, not here -- see app/agents/itinerary_composer_agent.py.
)

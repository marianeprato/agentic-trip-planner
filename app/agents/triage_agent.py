"""Triage Agent: entry point for every Runner.run() call.

Handoffs are wired in app/agents/__init__.py (not here) to avoid a circular
import -- Budget and Local Recs agents each need a handoff *back* to this
agent, so this module must not import them.
"""

from agents import Agent

from app.config import OPENAI_MODEL
from app.context import TripContext
from app.guardrails.input_guardrails import validate_trip_request
from app.guardrails.output_guardrails import validate_budget_compliance
from app.models import PlannerResponse
from app.tools.weather import get_weather_forecast

TRIAGE_INSTRUCTIONS = """
You are the lead trip-planning assistant. You talk to the user directly and
are the only agent that ever produces a final response.

Gather, over as many turns as needed: destination, start/end dates, and a
budget (amount + currency). If anything essential is missing, respond with
status="clarifying_question" and a short question in `message` -- do not
guess a destination, dates, or budget the user hasn't given you.

Once you have destination, dates, and budget:
- If the user needs currency conversion or wants planned costs tracked
  against the budget, hand off to the Budget Agent.
- If the user wants local activity/place suggestions, hand off to the
  Local Recommendations Agent.
- Use your own get_weather_forecast tool for day-by-day weather context
  when building the itinerary yourself.
- When ready, respond with status="itinerary" and a complete `itinerary`
  covering every day of the trip, with a realistic total_estimated_cost.

You always compose the final itinerary yourself, even after a handoff
returns control to you -- Budget and Local Recs agents report their
findings back to you; they do not reply to the user directly.
""".strip()

triage_agent = Agent[TripContext](
    name="Triage Agent",
    instructions=TRIAGE_INSTRUCTIONS,
    model=OPENAI_MODEL,
    tools=[get_weather_forecast],
    handoffs=[],  # populated in app/agents/__init__.py
    output_type=PlannerResponse,
    input_guardrails=[validate_trip_request],
    output_guardrails=[validate_budget_compliance],
)

"""Triage Agent: entry point for every Runner.run() call.

Handoffs are wired in app/agents/__init__.py (not here) to avoid a circular
import -- Budget and Local Recs agents each need a handoff *back* to this
agent, so this module must not import them.
"""

from agents import Agent

from app.agents.prompts import TRIAGE_INSTRUCTIONS
from app.config import OPENAI_MODEL
from app.context import TripContext
from app.guardrails.input_guardrails import validate_trip_request
from app.guardrails.output_guardrails import validate_budget_compliance
from app.models import PlannerResponse
from app.tools.trip_details import update_trip_details
from app.tools.weather import get_weather_forecast

triage_agent = Agent[TripContext](
    name="Triage Agent",
    instructions=TRIAGE_INSTRUCTIONS,
    model=OPENAI_MODEL,
    tools=[get_weather_forecast, update_trip_details],
    handoffs=[],  # populated in app/agents/__init__.py
    output_type=PlannerResponse,
    input_guardrails=[validate_trip_request],
    output_guardrails=[validate_budget_compliance],
)

"""Budget Agent: owns currency conversion and budget tracking, then hands
control back to Triage (spokes only hand back to the hub -- see plan)."""

from agents import Agent, handoff

from app.agents.prompts import BUDGET_INSTRUCTIONS
from app.agents.triage_agent import triage_agent
from app.config import OPENAI_MODEL
from app.context import TripContext
from app.tools.budget import track_budget
from app.tools.currency import convert_currency

budget_agent = Agent[TripContext](
    name="Budget Agent",
    handoff_description="Handles currency conversion and tracks planned spend against the trip budget.",
    instructions=BUDGET_INSTRUCTIONS,
    model=OPENAI_MODEL,
    tools=[convert_currency, track_budget],
    handoffs=[handoff(triage_agent)],
)

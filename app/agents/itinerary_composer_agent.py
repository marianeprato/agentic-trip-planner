"""Itinerary Composer Agent: writes the actual itinerary.

Runs on the stronger model (OPENAI_MODEL) -- reserved for the step that
benefits most from higher-quality reasoning, unlike Triage's routing
decisions which run on the cheaper OPENAI_ROUTING_MODEL. See README's
"Cost-aware model routing" section.

Like Budget/Local Recs, hands back to Triage (e.g. if it decides something
essential is genuinely still missing) rather than answering directly --
same star topology, same "spokes report to the hub" pattern, just a third
spoke. It also carries the same PlannerResponse output_type so it can
itself respond with status="clarifying_question" if that's simpler than a
round trip through Triage.
"""

from agents import Agent, handoff

from app.agents.prompts import ITINERARY_COMPOSER_INSTRUCTIONS
from app.agents.triage_agent import triage_agent
from app.config import OPENAI_MODEL
from app.context import TripContext
from app.guardrails.output_guardrails import validate_budget_compliance
from app.models import PlannerResponse
from app.tools.facts import get_place_facts
from app.tools.weather import get_weather_forecast

itinerary_composer_agent = Agent[TripContext](
    name="Itinerary Composer Agent",
    handoff_description=(
        "The default next step once destination, dates, budget, and return-visitor status are "
        "all known and the current message isn't an explicit ask for currency/expense help or "
        "local suggestions. Writes the full day-by-day itinerary itself -- finds its own points "
        "of interest, weather, and facts, so nothing needs to run before it."
    ),
    instructions=ITINERARY_COMPOSER_INSTRUCTIONS,
    model=OPENAI_MODEL,
    tools=[get_weather_forecast, get_place_facts],
    handoffs=[handoff(triage_agent)],
    output_type=PlannerResponse,
    output_guardrails=[validate_budget_compliance],
)

"""Local Recommendations Agent: owns POI search, plus weather to reason
about indoor/outdoor suggestions. Hands back to Triage when done.

output_type=SpokeFallbackResponse is defense-in-depth, not the normal
path. Confirmed live: this agent can call several tools across turns (POI
search, weather, facts, restaurants) and then reply directly instead of
calling the handoff-back tool -- reset_tool_choice (SDK default True)
reverts tool_choice to "auto" after any tool call, so
tool_choice="required" only guarantees the *first* turn isn't a bare
reply, not every turn.

The fallback used to be the full PlannerResponse -- on the assumption a
stray reply would come out as a harmless clarifying question. Also
confirmed live: it doesn't. The model filled in a complete,
itinerary-shaped PlannerResponse itself instead of handing back, which is
worse than the crash this was meant to prevent -- that itinerary skips
Composer's quality rules entirely, and this agent carries no budget output
guardrail, so it would reach the user completely unchecked.
SpokeFallbackResponse closes that: status="itinerary" isn't representable
in its schema at all, so a stray reply can only ever be a clarifying
question.
"""

from agents import Agent, ModelSettings, handoff

from app.agents.prompts import LOCAL_RECS_INSTRUCTIONS
from app.agents.triage_agent import triage_agent
from app.config import OPENAI_MODEL
from app.context import TripContext
from app.models import SpokeFallbackResponse
from app.tools.facts import get_place_facts
from app.tools.poi import search_points_of_interest
from app.tools.restaurants import get_nearby_restaurants
from app.tools.weather import get_weather_forecast

local_recs_agent = Agent[TripContext](
    name="Local Recommendations Agent",
    handoff_description=(
        "ONLY use when the user's current message explicitly asks for local activity/place "
        "suggestions or recommendations. Not a default step before building an itinerary -- "
        "the Itinerary Composer Agent already finds its own points of interest, restaurants, "
        "and facts and does not need this run first."
    ),
    instructions=LOCAL_RECS_INSTRUCTIONS,
    model=OPENAI_MODEL,
    model_settings=ModelSettings(tool_choice="required"),
    tools=[search_points_of_interest, get_weather_forecast, get_place_facts, get_nearby_restaurants],
    handoffs=[handoff(triage_agent)],
    output_type=SpokeFallbackResponse,
)

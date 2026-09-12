"""Local Recommendations Agent: owns POI search, plus weather to reason
about indoor/outdoor suggestions. Hands back to Triage when done."""

from agents import Agent, handoff

from app.agents.prompts import LOCAL_RECS_INSTRUCTIONS
from app.agents.triage_agent import triage_agent
from app.config import OPENAI_MODEL
from app.context import TripContext
from app.tools.facts import get_place_facts
from app.tools.poi import search_points_of_interest
from app.tools.restaurants import get_nearby_restaurants
from app.tools.weather import get_weather_forecast

local_recs_agent = Agent[TripContext](
    name="Local Recommendations Agent",
    handoff_description="Finds points of interest and activities, weighing weather conditions.",
    instructions=LOCAL_RECS_INSTRUCTIONS,
    model=OPENAI_MODEL,
    tools=[search_points_of_interest, get_weather_forecast, get_place_facts, get_nearby_restaurants],
    handoffs=[handoff(triage_agent)],
)

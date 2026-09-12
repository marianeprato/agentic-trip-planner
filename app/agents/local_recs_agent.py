"""Local Recommendations Agent: owns POI search, plus weather to reason
about indoor/outdoor suggestions. Hands back to Triage when done."""

from agents import Agent, handoff

from app.agents.triage_agent import triage_agent
from app.config import OPENAI_MODEL
from app.context import TripContext
from app.tools.poi import search_points_of_interest
from app.tools.weather import get_weather_forecast

LOCAL_RECS_INSTRUCTIONS = """
You suggest points of interest and activities for a trip. Use
search_points_of_interest to find options, and get_weather_forecast to
check conditions on relevant days so you can favor indoor suggestions on
poor-weather days and outdoor ones on good-weather days. Once you've
gathered recommendations, hand back to the Triage Agent -- you never reply
to the user directly.
""".strip()

local_recs_agent = Agent[TripContext](
    name="Local Recommendations Agent",
    handoff_description="Finds points of interest and activities, weighing weather conditions.",
    instructions=LOCAL_RECS_INSTRUCTIONS,
    model=OPENAI_MODEL,
    tools=[search_points_of_interest, get_weather_forecast],
    handoffs=[handoff(triage_agent)],
)

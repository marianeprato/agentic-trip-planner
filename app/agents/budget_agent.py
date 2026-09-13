"""Budget Agent: owns currency conversion and budget tracking, then hands
control back to Triage (spokes only hand back to the hub -- see plan).

output_type=SpokeFallbackResponse is defense-in-depth, not the normal
path: if the model ever forgets to call the handoff-back tool and just
replies directly instead (observed live -- see the Local Recs fix for the
same issue), tool_choice="required" makes that less likely on the very
first turn, but reset_tool_choice (SDK default True) reverts to "auto"
after any tool call, so it can still happen on a later turn.
SpokeFallbackResponse -- narrower than Triage/Composer's PlannerResponse --
makes status="itinerary" impossible to represent, so a stray reply can
only come out as a clarifying question: see that model's docstring for why
PlannerResponse itself turned out not to be a safe enough fallback here.
"""

from agents import Agent, ModelSettings, handoff

from app.agents.prompts import BUDGET_INSTRUCTIONS
from app.agents.triage_agent import triage_agent
from app.config import OPENAI_MODEL
from app.context import TripContext
from app.models import SpokeFallbackResponse
from app.tools.budget import track_budget
from app.tools.currency import convert_currency

budget_agent = Agent[TripContext](
    name="Budget Agent",
    handoff_description=(
        "Use when the user's current message asks a currency-conversion or expense-tracking "
        "question -- including a plain request like 'convert 150 GBP to EUR' or 'how much is "
        "my budget in euros', even if an itinerary was already produced earlier in the "
        "conversation. Do NOT use just because a budget amount was stated with no question "
        "attached, or because the destination's currency differs from the budget currency."
    ),
    instructions=BUDGET_INSTRUCTIONS,
    model=OPENAI_MODEL,
    model_settings=ModelSettings(tool_choice="required"),
    tools=[convert_currency, track_budget],
    handoffs=[handoff(triage_agent)],
    output_type=SpokeFallbackResponse,
)

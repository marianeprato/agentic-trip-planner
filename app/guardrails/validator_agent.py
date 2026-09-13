"""Small dedicated agent used only inside the input guardrail to catch
nonsensical destinations that plain parsing/regex can't (e.g. "Narnia").
Deliberately contrasted with the output guardrail, which is pure arithmetic
with no LLM call -- two different guardrail *styles*, both valid.

Uses the cheap routing model: this is a binary classification task (real
place or not), not generation -- see README's "Cost-aware model routing".
"""

from agents import Agent

from app.config import OPENAI_ROUTING_MODEL
from app.models import TripRequestValidation

trip_request_validator_agent = Agent(
    name="Trip Request Validator",
    instructions=(
        "You check ONLY whether a trip planning request refers to a real, plannable "
        "destination. Respond with is_valid=False only for clearly nonsensical, "
        "fictional, or impossible destinations (e.g. 'Narnia', 'the Moon', "
        "'Atlantis'). Real cities, countries, regions, or landmarks -- even "
        "obscure or misspelled ones -- should be is_valid=True. Give a brief "
        "one-sentence reasoning either way.\n\n"
        "Do NOT judge whether the stated budget is realistic or sufficient for "
        "the destination -- that is a separate check that runs later, after an "
        "itinerary is drafted, not your job. A real destination with an "
        "unrealistically low budget is still is_valid=True here."
    ),
    model=OPENAI_ROUTING_MODEL,
    output_type=TripRequestValidation,
)

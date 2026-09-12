"""Small dedicated agent used only inside the input guardrail to catch
nonsensical destinations that plain parsing/regex can't (e.g. "Narnia").
Deliberately contrasted with the output guardrail, which is pure arithmetic
with no LLM call -- two different guardrail *styles*, both valid.
"""

from agents import Agent

from app.config import OPENAI_MODEL
from app.models import TripRequestValidation

trip_request_validator_agent = Agent(
    name="Trip Request Validator",
    instructions=(
        "You check whether a trip planning request refers to a real, plannable "
        "destination. Respond with is_valid=False only for clearly nonsensical, "
        "fictional, or impossible destinations (e.g. 'Narnia', 'the Moon', "
        "'Atlantis'). Real cities, countries, regions, or landmarks -- even "
        "obscure or misspelled ones -- should be is_valid=True. Give a brief "
        "one-sentence reasoning either way."
    ),
    model=OPENAI_MODEL,
    output_type=TripRequestValidation,
)

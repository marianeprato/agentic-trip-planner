"""Wires the star handoff topology.

triage_agent is defined with handoffs=[] because Budget/Local Recs/Composer
each need a handoff *back* to Triage (import them and this would be
circular). Importing them here and then appending completes both
directions without a circular import.
"""

import logging
import os

from agents import RunContextWrapper, handoff

from app.agents.budget_agent import budget_agent
from app.agents.itinerary_composer_agent import itinerary_composer_agent
from app.agents.local_recs_agent import local_recs_agent
from app.agents.prompts import OPIK_PROMPT_NAMES
from app.agents.triage_agent import triage_agent
from app.context import TripContext


def _essentials_gathered(ctx: RunContextWrapper[TripContext], agent) -> bool:
    """Gate on TripContext.has_all_essentials() rather than trusting the
    routing model's judgment of when it's ready to hand off -- see that
    method's docstring for the live failure this closes. While this
    returns False, none of the three specialist handoff tools are even
    present in the model's tool list, so Triage cannot call them no matter
    what it decides; it can only call update_trip_details or reply with a
    clarifying question.
    """
    return ctx.context.has_all_essentials()


triage_agent.handoffs = [
    handoff(budget_agent, is_enabled=_essentials_gathered),
    handoff(local_recs_agent, is_enabled=_essentials_gathered),
    handoff(itinerary_composer_agent, is_enabled=_essentials_gathered),
]

__all__ = [
    "triage_agent",
    "budget_agent",
    "local_recs_agent",
    "itinerary_composer_agent",
    "sync_prompts_from_opik",
]

logger = logging.getLogger(__name__)

_AGENTS_BY_PROMPT_KEY = {
    "triage": triage_agent,
    "itinerary_composer": itinerary_composer_agent,
    "budget": budget_agent,
    "local_recs": local_recs_agent,
}


def sync_prompts_from_opik() -> None:
    """Best-effort: overwrite each agent's instructions in memory with the
    latest version from Opik's Prompt Library.

    Explicit opt-in call (used by app/main.py and scripts/cli_demo.py at
    startup) rather than something that runs on import -- see
    app/agents/prompts.py's docstring for why. Never raises: no
    OPIK_API_KEY, no network, or a prompt that hasn't been created yet in
    Opik (run scripts/seed_prompts.py first) all just leave the local
    default from app/agents/prompts.py in place.
    """
    if not os.environ.get("OPIK_API_KEY"):
        return

    import opik

    try:
        client = opik.Opik()
    except Exception:
        logger.warning("Could not create Opik client; keeping local default prompts.", exc_info=True)
        return

    for key, agent in _AGENTS_BY_PROMPT_KEY.items():
        prompt_name = OPIK_PROMPT_NAMES[key]
        try:
            prompt = client.get_prompt(name=prompt_name)
        except Exception:
            logger.warning("Could not fetch prompt %r from Opik; keeping local default.", prompt_name, exc_info=True)
            continue
        if prompt is not None:
            agent.instructions = prompt.prompt

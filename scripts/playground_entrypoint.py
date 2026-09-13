"""Opik Agent Playground entrypoint for the trip planner.

Launch with:
    uv run opik endpoint --project agentic-trip-planner -- uv run python scripts/playground_entrypoint.py

Then open the Agent Playground in the Opik UI and submit a message. The
result -- along with the full multi-agent trace (handoffs, tool calls) --
shows up there.

Uses a single fixed, reused session (PLAYGROUND_SESSION_ID) rather than a
fresh one per call: this project's interesting behavior (handoffs,
guardrails) only shows up after a few turns once destination/dates/budget
are known, so a fresh-session-per-run would almost always just dead-end on
the same clarifying question. Run scripts/reset_playground_session.py to
deliberately start a new conversation instead of continuing the last one.
"""

from __future__ import annotations

import asyncio
import threading

import opik

from app.agents import sync_prompts_from_opik
from app.config import require_openai_api_key
from app.orchestration import run_turn
from app.sessions import PLAYGROUND_SESSION_ID, get_context, get_session, save_context
from app.tracing import configure_tracing


async def _run_playground_turn(message: str) -> str:
    context = await get_context(PLAYGROUND_SESSION_ID)
    session = get_session(PLAYGROUND_SESSION_ID)

    result = await run_turn(message, session, context)
    await save_context(PLAYGROUND_SESSION_ID, context)

    output = result.output
    if output.status == "clarifying_question":
        return f"[{result.last_agent_name}] {output.message}"

    itinerary = output.itinerary
    lines = [
        f"[{result.last_agent_name}] Itinerary for {itinerary.destination} "
        f"({itinerary.start_date} to {itinerary.end_date}):"
    ]
    for day in itinerary.days:
        lines.append(f"  - {day.date}: {day.summary} (~{day.estimated_cost} {itinerary.currency})")
        for activity in day.activities:
            lines.append(f"      {activity.time} - {activity.description}")
            if activity.fun_fact:
                lines.append(f"          Fun fact: {activity.fun_fact}")
    lines.append(f"  Total estimated cost: {itinerary.total_estimated_cost} {itinerary.currency}")
    lines.append(f"  Within budget: {itinerary.within_budget}")
    return "\n".join(lines)


@opik.track(entrypoint=True)
def run_trip_planner(message: str) -> str:
    """Send one message to the trip planner's Triage Agent, using the fixed
    playground test session so multi-turn behavior is reachable across runs."""
    return asyncio.run(_run_playground_turn(message))


require_openai_api_key()
configure_tracing()
sync_prompts_from_opik()

if __name__ == "__main__":
    # opik endpoint registers run_trip_planner and dispatches playground
    # submissions to it via a background daemon thread it starts on import
    # (see opik.runner.activate). A daemon thread doesn't keep the process
    # alive by itself -- the main thread has to block, or the process exits
    # immediately (as it did on the first attempt at this) and takes the
    # runner thread down with it before it can serve anything.
    print(f"Playground entrypoint registered (session: {PLAYGROUND_SESSION_ID}). "
          f"Waiting for opik endpoint to dispatch runs -- Ctrl+C to stop.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass

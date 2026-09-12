"""Terminal chat loop exercising the full backend stack (agents, handoffs,
guardrails, MongoDB-backed sessions, tracing) without the FastAPI layer.

Usage:
    uv run python scripts/cli_demo.py [session_id]
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from agents import InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered, Runner

from app.agents import sync_prompts_from_opik, triage_agent
from app.config import require_openai_api_key
from app.models import PlannerResponse
from app.sessions import close_client, create_session, get_context, get_session, save_context
from app.tracing import configure_tracing


async def main() -> None:
    require_openai_api_key()
    configure_tracing()
    sync_prompts_from_opik()

    session_id = sys.argv[1] if len(sys.argv) > 1 else f"cli-{uuid.uuid4().hex[:8]}"
    print(f"Session: {session_id}  (Ctrl+D or 'quit' to exit)\n")

    await create_session(session_id)
    session = get_session(session_id)

    try:
        while True:
            try:
                user_input = input("you> ").strip()
            except EOFError:
                break
            if not user_input or user_input.lower() in {"quit", "exit"}:
                break

            context = await get_context(session_id)

            try:
                result = await Runner.run(triage_agent, user_input, session=session, context=context)
            except InputGuardrailTripwireTriggered as e:
                print(f"[input guardrail tripped] {e.guardrail_result.output.output_info}\n")
                continue
            except OutputGuardrailTripwireTriggered as e:
                print(f"[output guardrail tripped] {e.guardrail_result.output.output_info}\n")
                continue

            await save_context(session_id, context)

            output: PlannerResponse = result.final_output
            print(f"[agent: {result.last_agent.name}]")
            if output.status == "clarifying_question":
                print(f"assistant> {output.message}\n")
            else:
                itinerary = output.itinerary
                print(f"assistant> Itinerary for {itinerary.destination} "
                      f"({itinerary.start_date} to {itinerary.end_date}):")
                for day in itinerary.days:
                    print(f"  - {day.date}: {day.summary} (~{day.estimated_cost} {itinerary.currency})")
                    for activity in day.activities:
                        print(f"      {activity.time} - {activity.description}")
                        if activity.fun_fact:
                            print(f"          Fun fact: {activity.fun_fact}")
                print(f"  Total estimated cost: {itinerary.total_estimated_cost} {itinerary.currency}")
                print(f"  Within budget: {itinerary.within_budget}\n")
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())

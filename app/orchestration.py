"""Shared turn-execution logic used by the FastAPI routes, CLI demo, and
Playground entrypoint, so bounded-failure handling lives in one place
rather than being reimplemented three times.

Two failure modes are turned into a clear PlannerResponse instead of a raised
exception or a hard rejection:

1. Output guardrail rejection (itinerary over budget) -- the rejection
   reason is fed back to the model and it gets a bounded number of
   revision attempts before falling back to a clear "couldn't fit the
   budget" message.
2. Input guardrail rejection (implausible destination) -- returned as a
   clarifying question rather than an error, since there's nothing to
   automatically revise; the ball is back in the user's court.

A bounded max_turns also caps how many turns (model calls, including
handoffs) a single Runner.run can take, so a pathological Triage <->
specialist back-and-forth can't loop indefinitely -- it falls back to a
clear "unable to complete this request" message instead.

Both the revision limit and the turns limit are logged via custom_span()
(not just Python logging) specifically so they're visible in the trace
tree in the OpenAI/Opik dashboards, not just in application logs -- and the
whole turn (every revision attempt) is wrapped in one `trace()` so multiple
Runner.run calls for one user turn show up grouped together instead of as
unrelated top-level traces.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agents import (
    InputGuardrailTripwireTriggered,
    MaxTurnsExceeded,
    OutputGuardrailTripwireTriggered,
    Runner,
    custom_span,
    trace,
)
from agents.memory import Session

from app.agents import triage_agent
from app.api.streaming import map_stream_event, sse
from app.context import TripContext
from app.models import PlannerResponse

logger = logging.getLogger(__name__)

MAX_TURNS = 15
MAX_GUARDRAIL_REVISIONS = 2

_INPUT_REJECTED_TEMPLATE = "I couldn't process that: {reason} Could you clarify your request?"
_REVISION_LIMIT_TEMPLATE = (
    "I tried a few times but couldn't put together a plan that fits within your budget "
    "({reason}). Could you raise the budget or trim what you'd like to see?"
)
_MAX_TURNS_TEMPLATE = "This request needed more back-and-forth than expected -- could you simplify it or try again?"


@dataclass
class TurnResult:
    output: PlannerResponse
    last_agent_name: str


def _reason_from(guardrail_output_info: Any) -> str:
    if isinstance(guardrail_output_info, dict):
        return str(guardrail_output_info.get("reason", guardrail_output_info))
    return str(guardrail_output_info)


def _as_planner_response(final_output: Any) -> PlannerResponse:
    """Normalizes final_output to PlannerResponse regardless of which
    agent produced it. Triage/Composer already output PlannerResponse;
    Budget/Local Recs output the narrower SpokeFallbackResponse (see
    app/models.py) when they stray into a direct reply instead of handing
    back -- re-validating its dump against the wider schema fills in
    itinerary=None, which is always correct since that schema can't
    represent anything else.
    """
    if isinstance(final_output, PlannerResponse):
        return final_output
    return PlannerResponse.model_validate(final_output.model_dump())


async def _run_once(current_input: str, session: Session | None, context: TripContext) -> tuple[TurnResult | None, str | None]:
    """Runs Triage once. Returns (result, None) on success/resolved
    failure, or (None, rejection_reason) to signal "retry with this input"."""
    try:
        result = await Runner.run(triage_agent, current_input, session=session, context=context, max_turns=MAX_TURNS)
        return TurnResult(output=_as_planner_response(result.final_output), last_agent_name=result.last_agent.name), None
    except InputGuardrailTripwireTriggered as e:
        reason = _reason_from(e.guardrail_result.output.output_info)
        logger.info("Input guardrail rejected the request: %s", reason)
        output = PlannerResponse(status="clarifying_question", message=_INPUT_REJECTED_TEMPLATE.format(reason=reason))
        return TurnResult(output=output, last_agent_name="Triage Agent"), None
    except MaxTurnsExceeded:
        with custom_span("max_turns_exceeded", data={"max_turns": MAX_TURNS}):
            logger.warning("Max turns (%d) exceeded for this request.", MAX_TURNS)
        output = PlannerResponse(status="clarifying_question", message=_MAX_TURNS_TEMPLATE)
        return TurnResult(output=output, last_agent_name="Triage Agent"), None
    except OutputGuardrailTripwireTriggered as e:
        reason = _reason_from(e.guardrail_result.output.output_info)
        return None, reason


async def run_turn(user_input: str, session: Session | None, context: TripContext) -> TurnResult:
    """Run one user turn through Triage, with bounded guardrail-revision and
    bounded turns -- see module docstring."""
    current_input = user_input
    with trace("trip_planner_turn"):
        for attempt in range(MAX_GUARDRAIL_REVISIONS + 1):
            result, rejection_reason = await _run_once(current_input, session, context)
            if result is not None:
                return result

            if attempt >= MAX_GUARDRAIL_REVISIONS:
                with custom_span(
                    "guardrail_revision_limit_reached",
                    data={"max_revisions": MAX_GUARDRAIL_REVISIONS, "last_reason": rejection_reason},
                ):
                    logger.warning(
                        "Guardrail revision limit (%d) reached; giving up. Last reason: %s",
                        MAX_GUARDRAIL_REVISIONS,
                        rejection_reason,
                    )
                output = PlannerResponse(status="clarifying_question", message=_REVISION_LIMIT_TEMPLATE.format(reason=rejection_reason))
                return TurnResult(output=output, last_agent_name="Itinerary Composer Agent")

            with custom_span(
                "guardrail_revision_attempt", data={"attempt": attempt + 1, "max_revisions": MAX_GUARDRAIL_REVISIONS, "reason": rejection_reason}
            ):
                logger.info("Guardrail revision attempt %d/%d: %s", attempt + 1, MAX_GUARDRAIL_REVISIONS, rejection_reason)
            current_input = (
                f"The itinerary you just proposed was rejected for exceeding the budget: {rejection_reason}. "
                "Please revise it to fit within the stated budget."
            )

    raise AssertionError("unreachable: the loop always returns")


async def run_turn_streamed(user_input: str, session: Session | None, context: TripContext) -> AsyncIterator[str]:
    """Streaming counterpart to run_turn(), yielding SSE frames. Guardrail
    revisions surface as a {"type": "revising"} event between attempts
    rather than a terminal error, matching run_turn()'s non-streaming
    behavior -- the stream only ever ends in a final_output event, never a
    guardrail-caused error event.
    """
    current_input = user_input
    with trace("trip_planner_turn"):
        for attempt in range(MAX_GUARDRAIL_REVISIONS + 1):
            try:
                result = Runner.run_streamed(triage_agent, current_input, session=session, context=context, max_turns=MAX_TURNS)
                async for event in result.stream_events():
                    payload = map_stream_event(event)
                    if payload is not None:
                        yield sse(payload)
                final = _as_planner_response(result.final_output)
                yield sse({"type": "final_output", **final.model_dump()})
                return
            except InputGuardrailTripwireTriggered as e:
                reason = _reason_from(e.guardrail_result.output.output_info)
                logger.info("Input guardrail rejected the request: %s", reason)
                fallback = PlannerResponse(status="clarifying_question", message=_INPUT_REJECTED_TEMPLATE.format(reason=reason))
                yield sse({"type": "final_output", **fallback.model_dump()})
                return
            except MaxTurnsExceeded:
                with custom_span("max_turns_exceeded", data={"max_turns": MAX_TURNS}):
                    logger.warning("Max turns (%d) exceeded for this request.", MAX_TURNS)
                fallback = PlannerResponse(status="clarifying_question", message=_MAX_TURNS_TEMPLATE)
                yield sse({"type": "final_output", **fallback.model_dump()})
                return
            except OutputGuardrailTripwireTriggered as e:
                reason = _reason_from(e.guardrail_result.output.output_info)
                if attempt >= MAX_GUARDRAIL_REVISIONS:
                    with custom_span(
                        "guardrail_revision_limit_reached",
                        data={"max_revisions": MAX_GUARDRAIL_REVISIONS, "last_reason": reason},
                    ):
                        logger.warning(
                            "Guardrail revision limit (%d) reached; giving up. Last reason: %s",
                            MAX_GUARDRAIL_REVISIONS,
                            reason,
                        )
                    fallback = PlannerResponse(status="clarifying_question", message=_REVISION_LIMIT_TEMPLATE.format(reason=reason))
                    yield sse({"type": "final_output", **fallback.model_dump()})
                    return

                with custom_span(
                    "guardrail_revision_attempt", data={"attempt": attempt + 1, "max_revisions": MAX_GUARDRAIL_REVISIONS, "reason": reason}
                ):
                    logger.info("Guardrail revision attempt %d/%d: %s", attempt + 1, MAX_GUARDRAIL_REVISIONS, reason)
                yield sse({"type": "revising", "attempt": attempt + 1, "max_revisions": MAX_GUARDRAIL_REVISIONS, "reason": reason})
                current_input = (
                    f"The itinerary you just proposed was rejected for exceeding the budget: {reason}. "
                    "Please revise it to fit within the stated budget."
                )

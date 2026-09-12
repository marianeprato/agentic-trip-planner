"""HTTP routes wrapping the agent system.

Every Runner call here always starts at triage_agent (never resumed from
result.last_agent) so that Triage's input/output guardrails run on every
turn, regardless of which agent handled the previous turn -- see the plan's
build-order flag #2 for why this matters.
"""

from __future__ import annotations

import uuid

from agents import InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered, Runner
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agents import triage_agent
from app.api.schemas import (
    CreateSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    SessionStateResponse,
)
from app.api.streaming import map_stream_event, sse
from app.models import PlannerResponse
from app.sessions import create_session, get_context, get_session, save_context

router = APIRouter(prefix="/trips")


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_trip_session() -> CreateSessionResponse:
    session_id = uuid.uuid4().hex
    await create_session(session_id)
    return CreateSessionResponse(session_id=session_id)


@router.get("/sessions/{session_id}", response_model=SessionStateResponse)
async def get_trip_session(session_id: str) -> SessionStateResponse:
    context = await get_context(session_id)
    return SessionStateResponse(
        session_id=session_id,
        destination=context.destination,
        start_date=context.start_date.isoformat() if context.start_date else None,
        end_date=context.end_date.isoformat() if context.end_date else None,
        budget_amount=context.budget_amount,
        budget_currency=context.budget_currency,
        running_spent=context.running_spent,
    )


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(session_id: str, body: SendMessageRequest) -> PlannerResponse:
    context = await get_context(session_id)
    session = get_session(session_id)

    try:
        result = await Runner.run(triage_agent, body.message, session=session, context=context)
    except InputGuardrailTripwireTriggered as e:
        raise HTTPException(
            status_code=422,
            detail={"detail": "Input rejected.", "guardrail": "input", "reasoning": e.guardrail_result.output.output_info},
        ) from e
    except OutputGuardrailTripwireTriggered as e:
        raise HTTPException(
            status_code=422,
            detail={"detail": "Generated itinerary rejected.", "guardrail": "output", "reasoning": e.guardrail_result.output.output_info},
        ) from e

    await save_context(session_id, context)
    return result.final_output


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(session_id: str, body: SendMessageRequest) -> StreamingResponse:
    context = await get_context(session_id)
    session = get_session(session_id)

    async def event_generator():
        try:
            result = Runner.run_streamed(triage_agent, body.message, session=session, context=context)
            async for event in result.stream_events():
                payload = map_stream_event(event)
                if payload is not None:
                    yield sse(payload)

            await save_context(session_id, context)
            final: PlannerResponse = result.final_output
            yield sse({"type": "final_output", **final.model_dump()})
        except InputGuardrailTripwireTriggered as e:
            yield sse({"type": "error", "guardrail": "input", "reasoning": e.guardrail_result.output.output_info})
        except OutputGuardrailTripwireTriggered as e:
            yield sse({"type": "error", "guardrail": "output", "reasoning": e.guardrail_result.output.output_info})

    return StreamingResponse(event_generator(), media_type="text/event-stream")

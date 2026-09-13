"""HTTP routes wrapping the agent system.

Turn execution (guardrail-revision, bounded turns) lives in
app/orchestration.py, shared with the CLI demo and Playground entrypoint.
As of that module, guardrail rejections no longer raise out to here as
InputGuardrailTripwireTriggered/OutputGuardrailTripwireTriggered -- they
resolve to a clarifying-style PlannerResponse instead, so there is no
guardrail-specific 422 mapping here anymore; a rejected request is a normal
200 response explaining why, not a hard error.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    CreateSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    SessionStateResponse,
)
from app.models import PlannerResponse
from app.orchestration import run_turn, run_turn_streamed
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

    result = await run_turn(body.message, session, context)

    await save_context(session_id, context)
    return result.output


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(session_id: str, body: SendMessageRequest) -> StreamingResponse:
    context = await get_context(session_id)
    session = get_session(session_id)

    async def event_generator():
        async for frame in run_turn_streamed(body.message, session, context):
            yield frame
        await save_context(session_id, context)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

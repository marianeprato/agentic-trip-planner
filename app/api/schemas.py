"""Request/response models for the HTTP layer, kept separate from the
SDK-facing models in app/models.py."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.models import PlannerResponse


class CreateSessionResponse(BaseModel):
    session_id: str


class SendMessageRequest(BaseModel):
    message: str


class SessionStateResponse(BaseModel):
    session_id: str
    destination: str | None
    start_date: str | None
    end_date: str | None
    budget_amount: float | None
    budget_currency: str
    running_spent: float


class GuardrailErrorResponse(BaseModel):
    detail: str
    guardrail: Literal["input", "output"]
    reasoning: dict


# The plain /messages endpoint returns PlannerResponse as-is.
SendMessageResponse = PlannerResponse

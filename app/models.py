"""Pydantic models shared by tools, agents (as output_type), and the API layer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WeatherForecast(BaseModel):
    destination: str
    date: str
    condition: str
    temperature_high_c: float
    temperature_low_c: float
    precipitation_chance_pct: int


class PointOfInterest(BaseModel):
    name: str
    category: str
    description: str
    indoor: bool
    estimated_cost: float
    currency: str


class CurrencyConversionResult(BaseModel):
    amount: float
    from_currency: str
    to_currency: str
    converted_amount: float
    rate: float


class BudgetStatus(BaseModel):
    spent: float
    budget: float | None
    currency: str
    remaining: float | None
    over_budget: bool


class TripRequestValidation(BaseModel):
    is_valid: bool
    reasoning: str


class ItineraryDay(BaseModel):
    date: str
    summary: str
    activities: list[str]
    estimated_cost: float


class ItineraryOutput(BaseModel):
    destination: str
    start_date: str
    end_date: str
    currency: str
    days: list[ItineraryDay]
    total_estimated_cost: float
    budget_amount: float | None = None
    within_budget: bool = Field(
        default=True,
        description="Set by the agent's own estimate; the output guardrail independently re-checks this.",
    )


class PlannerResponse(BaseModel):
    """Triage agent's output_type.

    A single agent's output_type must be one fixed schema for every final
    response, so a plain "ask a clarifying question" turn and a "here's the
    itinerary" turn are both represented here via `status`, rather than by
    switching output_type on and off between turns.
    """

    status: Literal["clarifying_question", "itinerary"]
    message: str | None = Field(
        default=None, description="Set when status is 'clarifying_question'."
    )
    itinerary: ItineraryOutput | None = Field(
        default=None, description="Set when status is 'itinerary'."
    )

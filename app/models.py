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
    is_historical_estimate: bool = Field(
        default=False,
        description=(
            "True when the date was beyond Open-Meteo's forecast horizon and these "
            "values are a typical/seasonal estimate from past years' data instead of "
            "an actual forecast -- phrase advice accordingly (e.g. 'typically around', "
            "not 'it will be')."
        ),
    )


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


class PlaceFacts(BaseModel):
    place: str
    extract: str
    source_url: str | None = None


class ItineraryActivity(BaseModel):
    time: str = Field(description='Clock time, e.g. "9:00 AM".')
    description: str
    fun_fact: str | None = Field(
        default=None, description="A short, sourced fact about the place, if one was found."
    )


class ItineraryDay(BaseModel):
    date: str
    summary: str
    activities: list[ItineraryActivity]
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
    """Triage and Composer's output_type -- the two agents allowed to
    produce a final reply the user actually sees.

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


class SpokeFallbackResponse(BaseModel):
    """Budget and Local Recs' output_type -- deliberately narrower than
    PlannerResponse.

    Both agents are instructed to always hand back to Triage rather than
    reply directly, with output_type as defense-in-depth for the case
    where they don't (see their modules' docstrings). That defense-in-depth
    used to just be PlannerResponse, on the assumption a stray reply would
    come out as a harmless clarifying question -- but live testing showed
    the model can and does fill in a *complete, itinerary-shaped* reply
    instead, which is worse than the crash it was meant to prevent: that
    itinerary never goes through Composer's quality rules, and neither
    Budget nor Local Recs carries the budget output guardrail, so it would
    reach the user completely unchecked. Structured-output schema
    enforcement makes status="itinerary" impossible to represent here, so
    a stray reply can only ever come out as a clarifying question, no
    matter what the model intended.
    """

    status: Literal["clarifying_question"] = "clarifying_question"
    message: str

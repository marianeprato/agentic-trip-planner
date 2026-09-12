"""Lets the Triage Agent persist trip headline details (destination, dates,
budget) into TripContext once the user has stated them.

Without this, context.budget_amount would never get set from a real
conversation, which would silently disable the output budget guardrail (it
skips the check whenever budget_amount is None). track_budget only ever
recorded individual spend line-items, not these headline fields.
"""

from __future__ import annotations

from datetime import date

from agents import RunContextWrapper, function_tool

from app.context import TripContext


@function_tool
def update_trip_details(
    wrapper: RunContextWrapper[TripContext],
    destination: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    budget_amount: float | None = None,
    budget_currency: str | None = None,
    is_returning_visitor: bool | None = None,
    preferences: list[str] | None = None,
) -> str:
    """Record or update the trip's headline details as the user provides them.

    Call this as soon as the user states or changes any of these -- only
    pass the fields that are new or changed; omitted fields are left as-is.

    Args:
        destination: City, region, or country for the trip.
        start_date: ISO date string (YYYY-MM-DD).
        end_date: ISO date string (YYYY-MM-DD).
        budget_amount: Total trip budget.
        budget_currency: ISO currency code, e.g. "GBP", "USD", "EUR".
        is_returning_visitor: Whether the user has been to this destination before.
        preferences: Full replacement list of specific things the user wants
            to see/do this time (e.g. "Kinkaku-ji", "a sushi omakase dinner").
            Pass the complete list every time, not just new additions.
    """
    context = wrapper.context
    if destination is not None:
        context.destination = destination
    if start_date is not None:
        context.start_date = date.fromisoformat(start_date)
    if end_date is not None:
        context.end_date = date.fromisoformat(end_date)
    if budget_amount is not None:
        context.budget_amount = budget_amount
    if budget_currency is not None:
        context.budget_currency = budget_currency.upper()
    if is_returning_visitor is not None:
        context.is_returning_visitor = is_returning_visitor
    if preferences is not None:
        context.preferences = preferences
    return "Trip details updated."

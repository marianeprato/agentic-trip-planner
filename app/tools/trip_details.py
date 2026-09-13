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
    Do not call this again with the same values you already recorded --
    if the response says nothing changed, move on to your next step
    instead of calling it again.

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
    changed = False

    if destination is not None and destination != context.destination:
        context.destination = destination
        changed = True
    if start_date is not None:
        parsed = date.fromisoformat(start_date)
        if parsed != context.start_date:
            context.start_date = parsed
            changed = True
    if end_date is not None:
        parsed = date.fromisoformat(end_date)
        if parsed != context.end_date:
            context.end_date = parsed
            changed = True
    if budget_amount is not None and budget_amount != context.budget_amount:
        context.budget_amount = budget_amount
        changed = True
    if budget_currency is not None and budget_currency.upper() != context.budget_currency:
        context.budget_currency = budget_currency.upper()
        changed = True
    if is_returning_visitor is not None and is_returning_visitor != context.is_returning_visitor:
        context.is_returning_visitor = is_returning_visitor
        changed = True
    if preferences is not None and preferences != context.preferences:
        context.preferences = preferences
        changed = True

    if not changed:
        return f"Nothing changed -- these details were already recorded. {_next_step_instruction(context)}"
    return "Trip details updated."


def _next_step_instruction(context: TripContext) -> str:
    """Names the *specific* still-missing field and tells the model exactly
    what to do about it, rather than a generic "move on" -- confirmed live
    that generic feedback alone doesn't reliably break a cheap model's
    tendency to keep re-calling this tool instead of ever producing its
    final structured reply. Naming the exact gap and the exact required
    action leaves much less room for that.
    """
    if context.destination is None:
        return "You are still missing: destination. Do not call this tool again -- respond now with status='clarifying_question' and ask the user for the destination."
    if context.start_date is None or context.end_date is None:
        return "You are still missing: travel dates. Do not call this tool again -- respond now with status='clarifying_question' and ask the user for the dates."
    if context.budget_amount is None:
        return "You are still missing: the budget. Do not call this tool again -- respond now with status='clarifying_question' and ask the user for their budget."
    if context.is_returning_visitor is None:
        return (
            "You are still missing: whether the user has been to this destination before. "
            "Do not call this tool again -- respond now with status='clarifying_question' and ask "
            "the user directly whether they've been to the destination before."
        )
    return "Everything required is recorded. Do not call this tool again -- proceed to routing (a handoff, or the final itinerary) instead."

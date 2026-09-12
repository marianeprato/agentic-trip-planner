"""Budget tracking tool: the one tool that reads/writes shared RunContextWrapper state
instead of just taking LLM-provided arguments.

Assumes `amount` is already expressed in `context.budget_currency` -- the
Budget Agent's instructions tell it to call convert_currency first if the
user mentioned a cost in a different currency, then call this tool with the
converted amount. Budget tracking itself stays pure local logic; no
external API call.
"""

from __future__ import annotations

from agents import RunContextWrapper, function_tool

from app.context import BudgetLineItem, TripContext
from app.models import BudgetStatus


@function_tool
def track_budget(wrapper: RunContextWrapper[TripContext], item: str, amount: float) -> BudgetStatus:
    """Record a planned expense against the trip budget and return the updated status.

    Args:
        item: Short label for the expense, e.g. "Hotel (3 nights)".
        amount: Cost of the item, expressed in the trip's budget currency.
    """
    context = wrapper.context
    context.spend_log.append(BudgetLineItem(label=item, amount=amount, currency=context.budget_currency))
    context.running_spent += amount

    remaining = context.budget_amount - context.running_spent if context.budget_amount is not None else None
    return BudgetStatus(
        spent=context.running_spent,
        budget=context.budget_amount,
        currency=context.budget_currency,
        remaining=remaining,
        over_budget=remaining is not None and remaining < 0,
    )

"""Local run context shared across agents and tools for a single trip-planning session.

Never sent to the LLM — this is dependency injection for tools/guardrails,
distinct from the Session (conversation history), which the SDK persists
and sends to the LLM automatically. See app/sessions.py for how the two are
persisted alongside each other in MongoDB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class BudgetLineItem:
    label: str
    amount: float
    currency: str


@dataclass
class TripContext:
    destination: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget_amount: float | None = None
    budget_currency: str = "GBP"
    running_spent: float = 0.0
    spend_log: list[BudgetLineItem] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    is_returning_visitor: bool | None = None

    def has_all_essentials(self) -> bool:
        """Whether Triage has gathered everything it must ask for before
        routing to any specialist -- destination, both dates, a budget, and
        an answer to the return-visitor question. Used to gate the
        handoffs themselves (see app/agents/__init__.py's is_enabled=), not
        just as a prompt instruction: a cheap routing model has been
        observed live routing to a specialist (Budget, then separately
        Local Recs) on turn one, before ever asking the return-visitor
        question -- wording alone wasn't reliable enough to prevent it.
        """
        return (
            self.destination is not None
            and self.start_date is not None
            and self.end_date is not None
            and self.budget_amount is not None
            and self.is_returning_visitor is not None
        )

    def to_dict(self) -> dict:
        return {
            "destination": self.destination,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "budget_amount": self.budget_amount,
            "budget_currency": self.budget_currency,
            "running_spent": self.running_spent,
            "spend_log": [
                {"label": i.label, "amount": i.amount, "currency": i.currency}
                for i in self.spend_log
            ],
            "preferences": self.preferences,
            "is_returning_visitor": self.is_returning_visitor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TripContext":
        return cls(
            destination=data.get("destination"),
            start_date=date.fromisoformat(data["start_date"]) if data.get("start_date") else None,
            end_date=date.fromisoformat(data["end_date"]) if data.get("end_date") else None,
            budget_amount=data.get("budget_amount"),
            budget_currency=data.get("budget_currency", "GBP"),
            running_spent=data.get("running_spent", 0.0),
            spend_log=[
                BudgetLineItem(label=i["label"], amount=i["amount"], currency=i["currency"])
                for i in data.get("spend_log", [])
            ],
            preferences=data.get("preferences", []),
            is_returning_visitor=data.get("is_returning_visitor"),
        )

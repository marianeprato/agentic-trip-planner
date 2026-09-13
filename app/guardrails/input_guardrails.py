"""Input guardrail: validate_trip_request.

Runs cheap deterministic checks first (no LLM call), then falls back to a
small dedicated LLM agent for semantic destination checks that regex can't
catch. Registered with run_in_parallel=False: since a failed check should
gate the whole run, there's no reason to let the main agent start
generating (and spending tokens/tool calls) before this decides.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from agents import Agent, GuardrailFunctionOutput, RunContextWrapper, Runner, input_guardrail

from app.guardrails.validator_agent import trip_request_validator_agent
from app.models import TripRequestValidation

_MAX_DAYS_OUT = 730
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _find_dates(text: str) -> list[date]:
    found = []
    for match in _DATE_RE.findall(text):
        try:
            found.append(date.fromisoformat(match))
        except ValueError:
            continue
    return found


def _extract_user_text(item) -> str | None:
    role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)
    if role != "user":
        return None
    content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text") for p in content if isinstance(p, dict) and p.get("text")]
        if parts:
            return " ".join(parts)
    return None


def _latest_user_message(input_data: str | list) -> str:
    """Once a session has history, `input_data` is the *entire* conversation
    (every prior turn, including internal message ids and the agent's own
    JSON replies), not just the new message -- stringifying all of that and
    scanning it for dates is both wrong (validates old turns, not this one)
    and flaky (message ids can coincidentally contain digit runs). Only the
    user's latest message is what the deterministic date check should look
    at -- dates already validated on an earlier turn don't need re-checking.
    """
    if isinstance(input_data, str):
        return input_data
    for item in reversed(input_data):
        text = _extract_user_text(item)
        if text is not None:
            return text
    return ""


def _all_user_text(input_data: str | list) -> str:
    """Unlike the date check, the destination-plausibility LLM check needs
    the *whole* conversation's worth of user statements, not just the
    latest -- a destination is typically stated once and not repeated on
    every turn (e.g. "No, first time." has no destination in it at all).
    Restricting this to only the latest message (as the date check
    correctly does) made the destination check reject perfectly normal
    follow-up turns for having "no destination to validate" -- confirmed
    live. Only extracts clean user-authored text (never the assistant's own
    JSON replies or internal message ids), so this doesn't reintroduce the
    original message-id-pollution bug the narrowing was meant to fix.
    """
    if isinstance(input_data, str):
        return input_data
    parts = [text for item in input_data if (text := _extract_user_text(item)) is not None]
    return " ".join(parts)


@input_guardrail(run_in_parallel=False)
async def validate_trip_request(
    ctx: RunContextWrapper, agent: Agent, input_text: str | list
) -> GuardrailFunctionOutput:
    latest_message = _latest_user_message(input_text)

    dates = _find_dates(latest_message)
    if len(dates) >= 2:
        start, end = dates[0], dates[1]
        today = date.today()
        if end <= start:
            return GuardrailFunctionOutput(
                output_info={"reason": "End date is not after start date."},
                tripwire_triggered=True,
            )
        if start < today:
            return GuardrailFunctionOutput(
                output_info={"reason": "Start date is in the past."},
                tripwire_triggered=True,
            )
        if start > today + timedelta(days=_MAX_DAYS_OUT):
            return GuardrailFunctionOutput(
                output_info={"reason": f"Start date is more than {_MAX_DAYS_OUT} days out."},
                tripwire_triggered=True,
            )

    result = await Runner.run(trip_request_validator_agent, _all_user_text(input_text))
    validation: TripRequestValidation = result.final_output
    return GuardrailFunctionOutput(
        output_info={"reason": validation.reasoning},
        tripwire_triggered=not validation.is_valid,
    )

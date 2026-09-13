"""Maps agents SDK stream events (from Runner.run_streamed) to a small
discriminated-union JSON payload the frontend's agent-activity panel
consumes over SSE.

Guardrails still run the same way under run_streamed() -- a tripwire still
raises, just partway through consuming the stream. Since the 200 +
text/event-stream headers are already flushed by then, a guardrail trip
can't be a clean HTTP error status; app/orchestration.py's
run_turn_streamed() catches it and yields a terminal {"type":
"final_output", ...} frame instead, same as any other resolved turn -- the
stream never ends in an "error" event.
"""

from __future__ import annotations

import json
from typing import Any


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def map_stream_event(event: Any) -> dict[str, Any] | None:
    if event.type == "agent_updated_stream_event":
        return {"type": "agent_updated", "agent": event.new_agent.name}

    if event.type == "raw_response_event":
        data = event.data
        if getattr(data, "type", None) == "response.output_text.delta":
            return {"type": "message_delta", "delta": data.delta}
        return None

    if event.type == "run_item_stream_event":
        item = event.item
        if event.name == "handoff_occured":
            return {
                "type": "handoff",
                "from": item.source_agent.name,
                "to": item.target_agent.name,
            }
        if event.name == "tool_called":
            raw = item.raw_item
            return {
                "type": "tool_call",
                "tool": getattr(raw, "name", None),
                "arguments": getattr(raw, "arguments", None),
            }
        if event.name == "tool_output":
            return {"type": "tool_output", "output": str(item.output)}
        return None

    return None

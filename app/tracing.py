"""Wires Opik in alongside the SDK's native OpenAI tracing dashboard.

Deliberately uses add_trace_processor(), NOT set_trace_processors(): the
latter *replaces* the default processor list (which is what sends traces to
the native OpenAI dashboard), so using it here would silently drop native
tracing -- the opposite of the "compare both side by side" goal. Requires
OPIK_API_KEY (and optionally OPIK_WORKSPACE) to be set; OPENAI_API_KEY
alone is enough for native tracing.
"""

from agents import add_trace_processor
from opik.integrations.openai.agents import OpikTracingProcessor

from app.config import OPIK_PROJECT_NAME

_configured = False


def configure_tracing() -> None:
    global _configured
    if _configured:
        return
    add_trace_processor(OpikTracingProcessor(project_name=OPIK_PROJECT_NAME))
    _configured = True

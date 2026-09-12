"""One-time (or re-runnable) seed: pushes the local default agent
instructions into Opik's Prompt Library so there's something to edit there.

Safe to re-run -- Opik only creates a new version when the content actually
changed, so re-seeding with unmodified text is a no-op.

Usage:
    uv run python scripts/seed_prompts.py
"""

from __future__ import annotations

import opik

from app.agents.prompts import (
    BUDGET_INSTRUCTIONS,
    LOCAL_RECS_INSTRUCTIONS,
    OPIK_PROMPT_NAMES,
    TRIAGE_INSTRUCTIONS,
)
from app.config import require_openai_api_key  # noqa: F401  (ensures .env is loaded via app.config's load_dotenv())

_PROMPTS = {
    OPIK_PROMPT_NAMES["triage"]: TRIAGE_INSTRUCTIONS,
    OPIK_PROMPT_NAMES["budget"]: BUDGET_INSTRUCTIONS,
    OPIK_PROMPT_NAMES["local_recs"]: LOCAL_RECS_INSTRUCTIONS,
}


def main() -> None:
    client = opik.Opik()
    for name, text in _PROMPTS.items():
        prompt = client.create_prompt(name=name, prompt=text)
        print(f"{name}: version {prompt.version} ({prompt.commit})")


if __name__ == "__main__":
    main()

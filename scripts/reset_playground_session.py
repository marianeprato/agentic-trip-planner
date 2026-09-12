"""Wipes the fixed session scripts/playground_entrypoint.py reuses across
Opik Agent Playground runs, so you can deliberately start a fresh
conversation instead of continuing wherever the last round of testing left
off.

Usage:
    uv run python scripts/reset_playground_session.py
"""

from __future__ import annotations

import asyncio

from app.sessions import PLAYGROUND_SESSION_ID, clear_session, close_client


async def main() -> None:
    await clear_session(PLAYGROUND_SESSION_ID)
    await close_client()
    print(f"Cleared session {PLAYGROUND_SESSION_ID!r}.")


if __name__ == "__main__":
    asyncio.run(main())

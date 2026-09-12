"""Centralized environment configuration.

Loads .env once via python-dotenv and exposes settings read from
environment variables by name only. Never hardcode secret values here —
see CLAUDE.md's secret-handling rule.
"""

import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "agentic_trip_planner")

OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "agentic-trip-planner")


def require_openai_api_key() -> None:
    """Fail fast with a clear message if OPENAI_API_KEY is missing, without ever printing it."""
    if os.environ.get("OPENAI_API_KEY") is None:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )

"""Shared Mongo client backing both conversation history (MongoDBSession)
and trip state (a plain `trip_contexts` collection on the same client).

These are two separate persistence concerns that happen to share one
datastore: MongoDBSession persists message history automatically; a
TripContext is local run state the SDK knows nothing about; the API layer
is responsible for saving/loading it itself on every turn -- see
app/context.py's docstring and the plan's flag #5 for why conflating the
two is an easy, silent bug.
"""

from __future__ import annotations

from pymongo import AsyncMongoClient

from agents.extensions.memory.mongodb_session import MongoDBSession
from app.config import MONGODB_DATABASE, MONGODB_URI
from app.context import TripContext

_client: AsyncMongoClient | None = None

_CONTEXTS_COLLECTION = "trip_contexts"

# Fixed session reused across Opik Agent Playground runs (see
# scripts/playground_entrypoint.py) rather than a fresh one per call, so
# multi-turn behavior (handoffs, guardrails) is actually reachable.
PLAYGROUND_SESSION_ID = "opik-playground-test"


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(MONGODB_URI)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_session(session_id: str) -> MongoDBSession:
    return MongoDBSession(session_id, client=get_client(), database=MONGODB_DATABASE)


async def get_context(session_id: str) -> TripContext:
    db = get_client()[MONGODB_DATABASE]
    doc = await db[_CONTEXTS_COLLECTION].find_one({"_id": session_id})
    if doc is None:
        return TripContext()
    doc.pop("_id", None)
    return TripContext.from_dict(doc)


async def save_context(session_id: str, context: TripContext) -> None:
    db = get_client()[MONGODB_DATABASE]
    await db[_CONTEXTS_COLLECTION].replace_one(
        {"_id": session_id}, {"_id": session_id, **context.to_dict()}, upsert=True
    )


async def create_session(session_id: str) -> None:
    """Ensure a TripContext document exists for a brand-new session id."""
    db = get_client()[MONGODB_DATABASE]
    await db[_CONTEXTS_COLLECTION].update_one(
        {"_id": session_id},
        {"$setOnInsert": {"_id": session_id, **TripContext().to_dict()}},
        upsert=True,
    )


async def clear_session(session_id: str) -> None:
    """Wipe both the conversation history and TripContext for a session id."""
    session = get_session(session_id)
    await session.clear_session()
    db = get_client()[MONGODB_DATABASE]
    await db[_CONTEXTS_COLLECTION].delete_one({"_id": session_id})

"""FastAPI app entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents import sync_prompts_from_opik
from app.api.routes import router
from app.config import require_openai_api_key
from app.sessions import close_client
from app.tracing import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    require_openai_api_key()
    configure_tracing()
    sync_prompts_from_opik()
    yield
    await close_client()


app = FastAPI(title="Agentic Trip Planner", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

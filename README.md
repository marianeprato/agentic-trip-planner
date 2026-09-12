# Agentic Trip Planner

A trip itinerary planner built on the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/), designed to exercise the SDK's multi-agent primitives -- handoffs, guardrails, and sessions -- rather than a single agent with a large tool-calling loop.

## Architecture

### Multi-agent handoffs (star topology)

A **Triage Agent** is the sole entry point for every conversation turn and the only agent that ever produces a final response to the user. When a turn needs currency conversion or budget tracking, Triage hands off to a **Budget Agent**; when it needs local activity suggestions, it hands off to a **Local Recommendations Agent**. Both specialist agents hand control back to Triage rather than replying directly -- a strict star topology (hub-and-spoke, not a mesh) that keeps the handoff graph easy to reason about while still exercising genuine bidirectional handoffs.

Every `Runner.run()` call always starts at Triage, even mid-conversation. The alternative -- resuming a turn from whichever agent last had control -- would mean Triage's input/output guardrails (see below) simply don't run on turns a specialist agent handles directly, since input guardrails only run for the agent a run *starts* with. Always entering through Triage keeps guardrail coverage total and unconditional.

### Guardrails

Two different guardrail *styles*, deliberately contrasted:

- **Input guardrail** (`validate_trip_request`): cheap deterministic date checks (parses, ordered correctly, not in the past, not absurdly far out) run first with no model call; only if those pass does a small dedicated LLM agent check whether the destination is a real, plannable place at all (catching "Narnia"-style nonsense that no regex would catch). Registered to run *before* the main agent starts, not in parallel with it, since a rejected request should never spend tokens generating a response first.
- **Output guardrail** (`validate_budget_compliance`): pure arithmetic, no model call. Sums the produced itinerary's estimated costs and compares against the trip's stated budget with a small tolerance, independently of whatever the agent itself estimated.

### Sessions and context: two persistence layers, one datastore

Conversation history (what the model sees each turn) and trip state (destination, dates, budget, running spend) are deliberately kept as two separate mechanisms that happen to share one MongoDB instance:

- **`MongoDBSession`** -- the SDK's own session backend, persists message history automatically. Chosen over the SDK's default `SQLiteSession` specifically to work against a real document database rather than a local file.
- **`TripContext`** -- local run state, invisible to the model, read and written directly by tools (e.g. `track_budget` mutates `context.running_spent`). The SDK has no concept of this; the API layer is responsible for loading and saving a `TripContext` document per session on every turn, in a separate `trip_contexts` collection on the same client.

### Structured output across conversational and final turns

An agent's `output_type` fixes one schema for every final response it produces -- it can't return plain text on one turn and a structured itinerary on the next. Triage's output is therefore a single discriminated type, `PlannerResponse`, with a `status` of either `clarifying_question` (asking the user for missing information) or `itinerary` (the completed, structured plan). The output guardrail only checks budget compliance when `status == "itinerary"`.

### Tracing

Traces are sent to both the OpenAI platform's native tracing dashboard and a [Comet Opik](https://www.comet.com/site/products/opik/) project, side by side, via `add_trace_processor()` -- not `set_trace_processors()`, which would replace the default processor list and silently drop native tracing.

### Tools

| Tool | Backing |
|---|---|
| `get_weather_forecast` | Open-Meteo (free, keyless) |
| `search_points_of_interest` | Small in-repo mocked dataset |
| `convert_currency` | Frankfurter API (free, keyless) |
| `track_budget` | Local logic against `TripContext`, no external call |

`get_weather_forecast` and `search_points_of_interest` were kept keyless and free by design -- API key management and free-tier rate limits are orthogonal to what this project is testing. Open-Meteo's forecast horizon (~16 days) is shorter than the guardrail's allowed trip-planning window (up to ~2 years out); a request for weather too far in advance surfaces as a tool-call error the agent sees and can route around in its response, rather than a crash.

## Running locally

```bash
cp .env.example .env   # fill in OPENAI_API_KEY (and OPIK_API_KEY to enable Opik tracing)
docker compose up -d   # starts MongoDB on localhost:27017
uv sync
uv run python scripts/cli_demo.py
```

The CLI demo exercises the full stack -- handoffs, guardrails, sessions, tracing -- in a terminal chat loop, without the API layer.

To run the API instead:

```bash
uv run uvicorn app.main:app --reload
```

- `POST /trips/sessions` -- start a session
- `POST /trips/sessions/{session_id}/messages` -- send a message, get back a `PlannerResponse`
- `POST /trips/sessions/{session_id}/messages/stream` -- same, streamed over SSE (drives the web UI's live agent-activity view)
- `GET /trips/sessions/{session_id}` -- inspect current trip state

## Tests

```bash
uv run pytest
```

Guardrails and tool logic are tested directly (no model calls). Handoff routing is tested against the SDK's `ScriptedModel` test double, so the suite runs without a live API key.

## Frontend

A Next.js UI (`web/`) is planned as a separate, independently deployable app that talks to this API over HTTP/SSE -- not yet built.

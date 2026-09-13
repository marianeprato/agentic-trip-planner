# Agentic Trip Planner

A trip itinerary planner built on the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/), designed to exercise the SDK's multi-agent primitives -- handoffs, guardrails, and sessions -- rather than a single agent with a large tool-calling loop.

## Architecture

### Multi-agent handoffs (star topology)

A **Triage Agent** is the sole entry point for every conversation turn and the only agent the user ever talks to directly for clarifying questions. It never writes the itinerary itself -- once it has destination, dates, budget, and preferences, it hands off to an **Itinerary Composer Agent**, which does the actual writing. It also hands off to a **Budget Agent** for currency conversion/expense tracking, or a **Local Recommendations Agent** for activity suggestions. All three specialists hand control back to Triage rather than replying directly -- a strict star topology (hub-and-spoke, not a mesh) that keeps the handoff graph easy to reason about while still exercising genuine bidirectional handoffs.

Every `Runner.run()` call starts at Triage, even mid-conversation, with one deliberate exception (see below). The alternative -- resuming a turn from whichever agent last had control -- would mean Triage's input guardrail (see below) simply doesn't run on turns a specialist agent handles directly, since input guardrails only run for the agent a run *starts* with. Always entering through Triage keeps guardrail coverage total and unconditional, except where a turn is structurally routed around Triage entirely, in which case there's nothing new for that guardrail to check anyway (see next).

**Handoffs are gated on real state, not just prompted.** All three of Triage's handoffs (`Budget`, `Local Recs`, `Composer`) use `is_enabled=` bound to `TripContext.has_all_essentials()` (destination, both dates, budget, and an answer to the return-visitor question). While that's `False`, the handoff tools aren't even present in the routing model's tool list -- it's not just told not to hand off early, it structurally *can't*. This exists because it was observed live: the cheap routing model would sometimes route to a specialist on turn one, before ever asking the return-visitor question, no matter how the prompt worded the ordering.

**Defense-in-depth against a specialist skipping its handoff back:** Budget and Local Recs are instructed, and given `tool_choice="required"`, to never reply directly -- but `tool_choice="required"` only forces the *first* turn to be a tool call (the SDK resets it to `"auto"` after any tool call, specifically to avoid an infinite forced-tool loop), so a later turn can still slip through as a bare reply. This happened live twice, in two different ways: first as a raw string that crashed any caller expecting structured output, then -- after giving them `output_type=PlannerResponse` to fix that -- as a complete, itinerary-shaped reply that skipped Composer's writing rules and the budget guardrail entirely (neither agent carries it). Budget and Local Recs now use a deliberately narrower type, `SpokeFallbackResponse` (`status` fixed to `"clarifying_question"`, no `itinerary` field at all) -- schema enforcement makes a stray reply incapable of representing an itinerary, no matter what the model intended. `app/orchestration.py` normalizes it back into the wider `PlannerResponse` shape before it reaches a caller.

**Structural pre-routing around Triage for one specific, confirmed-unreliable decision** (`app/routing.py`): a follow-up explicitly asking to convert a cost or track an expense *after* an itinerary already exists in the conversation didn't reliably reach the Budget Agent -- Triage's `tool_choice="required"` only binds its first model call, and by the time this message arrives the history already contains a full itinerary; the cheap routing model would sometimes just re-emit it rather than reconsidering. Three rounds of prompt tightening on `TRIAGE_INSTRUCTIONS` narrowed but never eliminated this. The fix: a tiny, cheap classifier now runs before Triage on every turn, and -- only once `has_all_essentials()` is true, the same gate used above -- starts that turn directly from `budget_agent_direct`, a Budget Agent variant with *no handoff back to Triage at all*. That last part was itself a second live finding: letting Budget hand back to Triage as normal reintroduced the exact same failure through a different door -- Triage, regaining control with the original message still the most recent user turn in history, would re-decide to hand off to Budget *again*, confirmed live bouncing 2-3 times before either recovering or, once, losing track of `TripContext` entirely and re-asking for destination/dates/budget from scratch. Removing the handoff tool structurally, rather than instructing Budget not to use it, forces a direct answer instead -- `SpokeFallbackResponse.message` already carries the actual conversion result fine.

**Triage itself needed the same `tool_choice="required"` treatment**, for a related but distinct failure: with only one tool (`update_trip_details`) available before the essentials are gathered, the cheap routing model would sometimes get stuck calling it repeatedly with unchanged values instead of ever asking the next question -- and, separately, sometimes skip calling it at all and jump straight to asking about the one missing field, silently never recording what the user had just given it in the same message. Forcing the first turn to be a tool call fixes the second failure directly. The first failure needed a different fix: `update_trip_details`'s "nothing changed" response now names the *specific* still-missing field and states the exact required next action (e.g. *"You are still missing: whether the user has been to this destination before. Do not call this tool again -- respond now with..."*), rather than a generic "move on" -- generic feedback alone didn't reliably break the repetition, but naming the exact gap did.

### Cost-aware model routing

Triage's job -- deciding what to ask next, which specialist to hand off to -- is classification-shaped, not generation. It runs on a cheaper/faster model (`OPENAI_ROUTING_MODEL`, default `gpt-4o-mini`), as does the input guardrail's destination-plausibility check (same shape: a yes/no judgment, not writing). The Itinerary Composer Agent -- the step people actually judge the product by -- runs on the stronger model (`OPENAI_MODEL`, default `gpt-4.1-mini`). Budget and Local Recs stay on the stronger model too: their job is real tool orchestration (currency math, weighing weather against POI options), not pure routing.

This is a deliberate tradeoff, not a limitation: routing/classification quality is far less sensitive to model strength than a written itinerary is, so paying for the stronger model only where it matters keeps the system both cheaper and, if anything, more consistent (a weaker model asked to also *write* well is a worse bargain than a strong model reserved for exactly that).

### Guardrails, with bounded revision instead of a hard rejection

Two different guardrail *styles*, deliberately contrasted:

- **Input guardrail** (`validate_trip_request`): cheap deterministic date checks (parses, ordered correctly, not in the past, not absurdly far out) run first with no model call, against *only the latest user message* -- once a session has history, the guardrail's input is the *entire* conversation, and an earlier version of this scanned all of it for dates, which was flaky (it could misfire on internal message IDs from prior turns). Only if the date checks pass does a small dedicated LLM agent check whether the destination is a real, plannable place at all (catching "Narnia"-style nonsense that no regex would catch). Registered to run *before* the main agent starts, not in parallel with it, since a rejected request should never spend tokens generating a response first.
- **Output guardrail** (`validate_budget_compliance`): pure arithmetic, no model call. Sums the produced itinerary's estimated costs and compares against the trip's stated budget with a small tolerance, independently of whatever the agent itself estimated. Lives on the Itinerary Composer Agent (it moved there when Composer split off from Triage), not Triage.

Neither guardrail failure is a hard error to the caller (`app/orchestration.py`):

- An **input** rejection becomes a normal `clarifying_question` response explaining why, rather than an HTTP error -- there's nothing to automatically fix, so the ball goes back to the user.
- An **output** rejection (itinerary over budget) feeds the rejection reason back to the model and gives it up to `MAX_GUARDRAIL_REVISIONS` (2) revision attempts before falling back to a clear "couldn't fit the budget" message. Every attempt for one user turn is wrapped in a single `trace()` so they show up grouped together in the OpenAI/Opik dashboards instead of as unrelated top-level traces, and both the per-attempt revision and hitting the limit are recorded via `custom_span()` -- specifically so they're visible in the trace tree itself, not just in application logs.

A `max_turns` bound (15) on the underlying `Runner.run()` calls also caps how many turns (model calls, including handoffs) one call can take, so a pathological Triage↔specialist back-and-forth can't loop indefinitely -- it falls back to a clear "this needed more back-and-forth than expected" message instead of hanging or erroring, also logged via `custom_span()`.

### Sessions and context: two persistence layers, one datastore

Conversation history (what the model sees each turn) and trip state (destination, dates, budget, running spend) are deliberately kept as two separate mechanisms that happen to share one MongoDB instance:

- **`MongoDBSession`** -- the SDK's own session backend, persists message history automatically. Chosen over the SDK's default `SQLiteSession` specifically to work against a real document database rather than a local file.
- **`TripContext`** -- local run state, invisible to the model, read and written directly by tools (e.g. `track_budget` mutates `context.running_spent`). The SDK has no concept of this; the API layer is responsible for loading and saving a `TripContext` document per session on every turn, in a separate `trip_contexts` collection on the same client.

### Structured output across conversational and final turns

An agent's `output_type` fixes one schema for every final response it produces -- it can't return plain text on one turn and a structured itinerary on the next. Triage and Composer -- the only two agents allowed to produce a reply the user actually sees -- share a discriminated type, `PlannerResponse`, with a `status` of either `clarifying_question` or `itinerary`. Budget and Local Recs deliberately use a narrower type instead, `SpokeFallbackResponse` (see above), that can only ever represent a clarifying question: they should never be the one producing the user-facing reply at all, so their fallback type shouldn't be *capable* of a full itinerary either. The output guardrail only checks budget compliance when `status == "itinerary"`, which only `PlannerResponse` can express.

### Tracing

Traces are sent to both the OpenAI platform's native tracing dashboard and a [Comet Opik](https://www.comet.com/site/products/opik/) project, side by side, via `add_trace_processor()` -- not `set_trace_processors()`, which would replace the default processor list and silently drop native tracing.

### Prompt management

Agent instructions are versioned in Opik's Prompt Library (included on the free Comet-hosted tier) rather than only living in code. `app/agents/prompts.py` holds the local default for each agent -- what it's constructed with, and what it falls back to if Opik is unreachable or a prompt hasn't been created there yet. `sync_prompts_from_opik()` is an explicit opt-in step (called once at startup by both `app/main.py` and `scripts/cli_demo.py`, never at import time) that overwrites each agent's instructions in memory with the latest version from Opik. This means editing a prompt in the Opik UI takes effect on the next app restart, no code change or redeploy needed -- while imports (and the test suite) stay network-free, since resolution never runs as an import-time side effect.

Run `uv run python scripts/seed_prompts.py` once to push the local defaults into Opik so there's something to edit; re-running it is a no-op unless the local text has changed (Opik only creates a new version when content actually differs).

### Tools

| Tool | Backing | Used by |
|---|---|---|
| `update_trip_details` | Local logic against `TripContext`, no external call | Triage |
| `get_weather_forecast` | Open-Meteo (free, keyless), with a historical-estimate fallback | Composer, Local Recs |
| `get_place_facts` | Wikipedia search + summary REST APIs (free, keyless) | Composer, Local Recs |
| `search_points_of_interest` | Wikipedia GeoSearch API (free, keyless) | Local Recs |
| `convert_currency` | Frankfurter API (free, keyless) | Budget |
| `track_budget` | Local logic against `TripContext`, no external call | Budget |

All the free/keyless external APIs were a deliberate choice -- API key management and paid-tier friction are orthogonal to what this project is testing -- but each comes with a real-world rough edge worth knowing about, all handled explicitly rather than papered over:

- **Open-Meteo's forecast horizon** (~16 days) is shorter than the guardrail's allowed trip-planning window (up to ~2 years out). Rather than erroring, `get_weather_forecast` falls back to a seasonal estimate built from the same calendar week in last year's historical archive (`WeatherForecast.is_historical_estimate=True`), so a far-out trip still gets genuine "what to pack" advice, phrased as typical conditions rather than a firm forecast. The historical archive endpoint also has no "probability of precipitation" field (that's a forecast-only concept) -- Open-Meteo silently returns `null` for it rather than erroring, so the historical path uses `precipitation_sum` instead, converted to a chance-of-rain proxy (the fraction of reference days that saw measurable rain).
- **Wikipedia's summary endpoint** needs an exact page title -- a query like "Kinkaku-ji, Kyoto" (the natural form for a geocoding-based tool) 404s against it directly. `get_place_facts` resolves the title via Wikipedia's own search API first, then fetches the summary for the resolved page.
- Wikipedia's public API rejects requests with a generic/default `User-Agent` header -- every Wikipedia-backed tool sends a descriptive one per its usage policy.
- **`search_points_of_interest` replaced the original hardcoded 5-city dataset** with Wikipedia's GeoSearch API, geocoded through the same Open-Meteo geocoder the weather tool uses. Two real limitations were found and deliberately accepted rather than engineered around: GeoData's search radius is hard-capped at 10km and not configurable, so a famous but geographically spread-out landmark can fall outside it (confirmed live -- Kinkaku-ji and Fushimi Inari Taisha are both more than 10km from Kyoto's geocoded center and never appear); and `prop=pageviews` combined with a generator query was tried as a popularity filter but confirmed live to silently return missing data for genuinely high-traffic pages (Nijō Castle came back with no pageviews data at all despite averaging ~150/day), so results are left in Wikipedia's own distance-sorted order rather than shipping a "popularity ranking" that quietly lies for some results. The Local Recommendations Agent is instructed to use its own judgment picking worthwhile places from the list rather than trusting every result is an attraction.

**Restaurant recommendations were deliberately removed from scope.** An earlier version named specific restaurants via OpenStreetMap's Overpass API, geocoded through Nominatim. Live testing surfaced two compounding problems: Overpass's free public mirrors have no SLA and can fail entirely under load (confirmed live -- all three independent mirrors down at once), and when that happened the model did not reliably fall back to an honest "no confirmed restaurant" response -- it named specific, plausible-sounding restaurants from its own training-data memory on most days of a week-long itinerary, despite an explicit instruction not to. That's a correctness problem a prompt instruction alone couldn't hold under real infrastructure failure, and it scales with itinerary length (more meals, more chances to fail). Rather than paper over it with retries or a narrower fallback prompt, restaurant suggestions were removed from the product entirely -- the assistant plans activities, not where to eat.

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
- `POST /trips/sessions/{session_id}/messages/stream` -- same, streamed over SSE (drives the web UI's live agent-activity view); a guardrail revision surfaces as a `{"type": "revising"}` event between attempts, matching the non-streaming endpoint's behavior of never treating a guardrail rejection as a hard error
- `GET /trips/sessions/{session_id}` -- inspect current trip state

### Opik Agent Playground

`scripts/playground_entrypoint.py` wires the trip planner up to [Opik's Agent Playground](https://www.comet.com/docs/opik/development/agent-playground) for interactive testing and prompt iteration from the browser:

```bash
uv run opik endpoint --project agentic-trip-planner -- uv run python scripts/playground_entrypoint.py
```

It reuses one fixed session (`opik-playground-test`) across Playground runs rather than a fresh one per call -- this project's interesting behavior (handoffs, guardrails, revision) only shows up after a few turns once destination/dates/budget are known, so a fresh session every time would almost always just dead-end on the same clarifying question. Run `scripts/reset_playground_session.py` to deliberately start over instead of continuing the last conversation.

**Stop it before relaunching.** The entrypoint blocks forever by design (see its own comments) so `opik endpoint` can keep dispatching runs to it -- there's no automatic exit. Relaunching without stopping the previous instance first leaves it running as an orphaned process forever, and having multiple registered runners for the same project can make the Playground route to an unpredictable one of them. Stop cleanly with:

```bash
uv run opik endpoint stop --project agentic-trip-planner
# or, to clear every runner regardless of project:
uv run opik endpoint stop --all
```

(Learned the hard way during development -- dozens of these accumulated silently over a single session before this was caught.)

### Running the API in Docker

An optional, standalone path for running the API itself in a container (the `uv run uvicorn --reload` command above stays the primary local dev loop):

```bash
docker build -t agentic-trip-planner .
docker compose up -d   # MongoDB on localhost:27017
docker run --rm -p 8000:8000 --env-file .env -e MONGODB_URI=mongodb://host.docker.internal:27017 agentic-trip-planner
```

## Tests

```bash
uv run pytest
```

Guardrails and tool logic are tested directly (no model calls). Handoff routing, the guardrail-revision loop, and the bounded-turns fallback are tested against the SDK's `ScriptedModel` test double, so the full suite runs without a live API key -- this is also what CI (`.github/workflows/ci.yml`) runs on every push and pull request.

## Frontend

A Next.js UI (`web/`) is planned as a separate, independently deployable app that talks to this API over HTTP/SSE -- not yet built.

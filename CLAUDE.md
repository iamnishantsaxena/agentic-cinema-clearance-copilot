# Clearance Copilot

Built for the **Google Cloud Agentic Cinema Hackathon** (Parallel partner track). Deadline: Sept 7, 2026 2pm PT. Full hackathon rules/guardrails this project was built under: [docs/hackathon-skill.md](docs/hackathon-skill.md). Original architecture plan: [docs/PLAN.md](docs/PLAN.md).

## What this is

An agent that reads a screenplay and produces a cited legal/rights clearance risk memo — real people, trademarks, songs, quotes, "based on true events" claims, real locations — so indie producers get a credible first-pass clearance report without paying $5-15k to outside counsel. Parallel's Search API is load-bearing: clearance/litigation/trademark status is live and can't come from a static index, which is the whole reason this idea doesn't read as a generic tech demo.

**Not legal advice.** Every report carries a disclaimer and flags items needing attorney review — see the citation-grounding control below.

## Hackathon constraints (non-negotiable)

- Agent framework must be Gemini + Google ADK. Accepted SDKs (must be actually imported/called, not just in requirements.txt): `google-adk`, `google-genai`, `google-generativeai`, `google-cloud-aiplatform`.
- No non-Google LLM tooling anywhere.
- Parallel Search API must be genuinely used at runtime — it is, in `backend/agents/tools.py`.
- Public repo, OSS license detectable in GitHub's "About" section (MIT, at repo root).
- Judged equally on Technological Implementation / Design / Potential Impact / Quality of Idea.

## Architecture (as actually built — differs from docs/PLAN.md in a few places)

Three-stage pipeline, orchestrated as **plain `async` Python**, not nested ADK agent composition:

1. `backend/agents/extractor.py` — `extractor_agent` (`LlmAgent`, Gemini 3.1 Flash Lite) reads the raw script text/PDF and emits `EntityList` (wraps `list[Entity]` — ADK's `output_schema` needs a single `BaseModel`, not a bare generic).
2. `backend/agents/researcher.py` — `assess_entity(entity)` runs a **fresh `Runner`/session per entity**, calling `research_entity_web` (Parallel Search, wrapped as an ADK tool in `tools.py`) and emitting a `RiskAssessment`. Fan-out across entities happens in `pipeline.py` via `asyncio.gather` + `asyncio.Semaphore(5)` — **not** a custom `BaseAgent`/`Event`-yielding node. We looked at that pattern (it needs `agent.clone()` + per-branch `InvocationContext`s + manually yielding `Event`s to get state persisted) and it buys nothing here since each entity's research is fully independent — running N separate `Runner.run_async()` calls concurrently does the identical thing with far less code.
3. `backend/agents/synthesizer.py` — one call over all assessments → `ReportSummary` (overall tier + executive summary).

`backend/agents/pipeline.py` — `analyze_script(script_text, script_title) -> Report` ties all three together. This is the vertical-slice entry point.

### Why not `SequentialAgent`?

The installed `google-adk` is **2.6.2**, notably newer than what most public ADK tutorials describe. `SequentialAgent`/`ParallelAgent` still work but are `@deprecated` in favor of a `Workflow`/`Node` graph system that can't yet host an `LlmAgent` as a sub-agent — so for now, plain `async` orchestration calling each `LlmAgent` via its own `Runner` is both simpler and the not-deprecated path. Still 100% genuine ADK usage (`LlmAgent`, `Runner`, `InMemorySessionService`, `FunctionTool` auto-wrapping) — the requirement is real ADK usage, not a specific composition primitive.

### Other real-API gotchas we hit (worth knowing before touching this code)

- `output_schema` on an `LlmAgent` writes a **plain `dict`** to `session.state[output_key]`, not the Pydantic instance — always re-validate with `Model.model_validate(...)`.
- `output_schema` does *not* require disabling tools or transfer callbacks (older docs said otherwise) — tools and structured output work together fine.
- The real `parallel-web` SDK call is `client.search(*, objective, search_queries, mode="turbo"|"basic"|"advanced", max_chars_total, ...)`, returning `SearchResult.results: list[WebSearchResult(url, title, excerpts: list[str], publish_date)]`. There's no `beta.search`, no `processor=`, no per-result `max_results` param — the plan doc's original sketch had this wrong; `tools.py` has the verified real signature.
- Passing a plain `async def` function in `LlmAgent(tools=[...])` still auto-wraps it as a `FunctionTool` — no manual wrapping needed.
- `gemini-2.5-flash` 404s for new API keys ("no longer available to new users") even though it still appears in `client.models.list()`. The three `LlmAgent`s pin `gemini-3.1-flash-lite` — chosen deliberately as the cheapest/lowest-tier current Gemini model to minimize cost, not just because it was the first one that worked. If this breaks again, list live models with `client.models.list()` and re-verify candidates with a real `generate_content` call (list membership isn't sufficient, since deprecated-for-new-keys models still show up there).
- Free-tier quota on this key is *per-model* and mostly *per-day*, not just per-minute: `gemini-3.6-flash` capped at 20 requests/day, `gemini-2.0-flash` and `gemini-2.0-flash-lite` are capped at 0 (effectively retired for free-tier keys), and `gemini-3.1-flash-lite`/`gemini-flash-lite-latest` were the only candidates with real headroom. Check `RESOURCE_EXHAUSTED` error bodies for `quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier` vs `PerMinute` before assuming a concurrency fix will help — a per-day cap won't budge no matter how much you throttle `MAX_CONCURRENT_RESEARCH`.

### Citation-grounding control (do not remove)

`researcher.py`'s `make_research_tool(seen_urls)` factory collects every URL Parallel actually returned during that entity's research turn. After the LLM emits a `RiskAssessment`, `assess_entity()` filters `citations` down to only URLs in `seen_urls` — a model-hallucinated citation can never survive into a report. This is the product's core credibility feature given the legal-risk framing; don't bypass it for convenience.

## Status / what's left

Done: repo scaffold, schemas, full agent pipeline (extractor → fan-out researcher → synthesizer), `samples/sample_script.txt` test fixture, FastAPI wrapper (`POST /api/analyze`, `GET /api/reports/{id}`, Firestore persistence via `backend/storage.py`), SSE live-progress (`backend/progress.py` + `GET /api/reports/{id}/stream`), and the full Jinja2 + Tailwind frontend (`/`, `/reports/{id}/processing`, `/reports/{id}` — screenplay/coverage-report visual identity, see `backend/templates/`). Verified end-to-end multiple times against real Parallel Search + real Firestore (project `sigma-sunlight-379504`, ADC via `gcloud auth application-default login`).

**Cloud Run deploy blocked, not yet attempted for real**: `sigma-sunlight-379504` (the project with full local access and the working Firestore data) has billing disabled, and both billing accounts on this Google account (`nishantksaxena29@gmail.com`) are closed. The other available project, `dashboardworx`, has billing enabled but this account only has `roles/viewer` there — not enough to enable APIs or deploy. Deployment needs one of: (a) reactivate/add a billing account and link it to `sigma-sunlight-379504`, or (b) get Editor/Owner on `dashboardworx`. Dockerfile is already written and untested against a real build.

Remaining build order (see [docs/PLAN.md](docs/PLAN.md) for full detail):
1. Resolve the billing/permissions blocker above, then: Dockerize (build/test the existing `Dockerfile` locally), deploy to Cloud Run, wire Secret Manager for `GOOGLE_API_KEY`/`PARALLEL_API_KEY` (never as plain env vars).
2. Polish: README run instructions, sample scripts for judges, error/empty states.

## Running locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GOOGLE_API_KEY and PARALLEL_API_KEY
python -m backend.agents.extractor samples/sample_script.txt   # test extraction alone
python -m backend.agents.pipeline samples/sample_script.txt    # full pipeline, prints a Report as JSON
```

## Cut from v1 (deliberate, not oversight)

No auth (reports reachable via unguessable UUID URL only), no Cloud Storage (PDFs inlined to Gemini directly), no job queue (in-memory `asyncio` is enough at demo scale), no `.fdx` parser. See [docs/PLAN.md](docs/PLAN.md) "Cut from v1" for the full list and reasoning — these are documented tradeoffs, not gaps to silently fix.

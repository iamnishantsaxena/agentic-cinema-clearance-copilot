# Original Architecture Plan

This is the design plan produced before writing any code. Some implementation
details evolved once we read the real installed library APIs (see
[CLAUDE.md](../CLAUDE.md) for what's actually true today — notably, `google-adk`
2.6.2 deprecated `SequentialAgent`, so the pipeline uses plain `async`
orchestration instead of nested ADK agent composition, and the real
`parallel-web` SDK signature differs from what's sketched below). Kept as-is
for the original reasoning on data layer, cut-vs-keep decisions, and build
order, which are all still accurate.

---

# Clearance Copilot — Google Cloud Agentic Cinema Hackathon (Parallel track)

## Context

Building for the Google Cloud Agentic Cinema Hackathon (deadline Sept 7, 2026, ~5 weeks out). Chosen idea: **Clearance Copilot** — an agent that reads a screenplay and produces a cited rights/legal clearance risk memo (real people, trademarks, songs, quotes, "based on true events" claims, distinctive real locations), so indie producers get a credible first-pass clearance report without paying $5-15k to outside counsel. Parallel's Search API is load-bearing here because clearance/litigation/trademark status is live and can't come from a static index — this is why the idea scored well on "Quality of Idea" (non-obvious, genuinely necessary partner use) rather than reading as a generic tech demo.

Hard constraints from hackathon rules: Gemini + Google ADK as the agent framework (accepted SDKs: `google-adk`, `google-genai`, `google-generativeai`, `google-cloud-aiplatform` — must be actually imported/called), no non-Google LLM tooling anywhere, Parallel Search API genuinely used at runtime (not decorative), public repo with detectable OSS license, hosted + runnable from source, judged equally on Technological Implementation / Design / Potential Impact / Quality of Idea.

## Architecture (original sketch — see CLAUDE.md for current)

**Pipeline**: `SequentialAgent` (ADK) with 3 stages, all writing structured Pydantic output into `session.state` via `output_schema`/`output_key`:

1. **Extractor** (`LlmAgent`) — Gemini reads the screenplay PDF/text directly (native multimodal PDF understanding — no Document AI, no PDF-parsing lib) and emits `list[Entity]`.
2. **Research + Assess fan-out** — `ResearchFanOutAgent(BaseAgent)` with a custom `_run_async_impl` that `asyncio.gather`s (capped at `Semaphore(5)`) N invocations of `ResearcherAssessorAgent`, one per entity.
   - `ResearcherAssessorAgent` (`LlmAgent`) — single LLM turn per entity: calls the `research_entity_web` tool (wraps Parallel Search), then emits a structured `RiskAssessment` directly.
   - `ponytail:` fixed `Semaphore(5)` concurrency cap, not adaptive backoff — fine for 10-40 entities per script; add real rate-limit handling if testing shows throttling.
3. **Synthesizer** (`LlmAgent`) — one call over all `RiskAssessment`s → executive summary + overall risk tier → final `Report`.

**Critical integrity control (non-negotiable)**: after `ResearcherAssessorAgent` emits a `RiskAssessment`, programmatically filter its `citations` to only URLs that actually appear in that turn's captured `research_entity_web` results. Never let a model-generated citation URL pass through unchecked — this is the product's core credibility feature (avoids hallucinated legal citations) and directly addresses the biggest execution risk identified during idea selection.

## Schemas (`backend/schemas.py`)

- `Entity`: `id, name, entity_type: Literal["real_person","trademark_brand","song_music","direct_quote","true_events_claim","real_location"], script_context, page_or_scene_ref`
- `SearchCitation`: `url, title, publish_date: str | None, excerpt`
- `RiskAssessment`: `entity_id, risk_tier: Literal["low","medium","high","critical"], confidence: Literal["low","medium","high"], rationale, citations: list[SearchCitation], attorney_review_required: bool, last_checked`
- `Report`: `report_id, script_title, generated_at, overall_risk_tier, executive_summary, entity_assessments: list[RiskAssessment], disclaimer` (disclaimer is a hardcoded constant string, never model-generated)

## Data layer

- **No Cloud Storage** — screenplay PDFs are inlined directly to Gemini as bytes (`types.Part.from_bytes`), well under inline size limits. Add later only if >20MB uploads are needed.
- **Firestore**: one collection `reports`, one denormalized doc per report (full `Report` JSON, `report_id` as doc ID). No separate entities/findings collections — nothing queries those independently in v1.
- `backend/storage.py`: three plain functions (`save_report`, `get_report`, `list_reports`) calling the Firestore client directly — no repository abstraction for a single backend.
- **Live progress**: in-memory per-job `asyncio.Queue` + Server-Sent Events from the FastAPI handler directly. No Pub/Sub.
  - `ponytail:` in-memory queue assumes a single Cloud Run instance — fine for demo; needs Pub/Sub if scaled to multi-instance later.

## Frontend

**FastAPI + Jinja2 + HTMX + Tailwind (CDN), not Next.js** — one language, one deploy target (same Cloud Run container, no CORS split), zero build step, and HTMX's SSE extension maps directly onto live agent-progress display with almost no JS. Judging rewards coherent UX, not framework choice.

Screens: `/` (upload) → `/reports/{id}/processing` (SSE step log: "Extracted 17 entities" / "Researching Coca-Cola..." / "Synthesizing report", redirects on completion) → `/reports/{id}` (risk-tier badge header, persistent "Not legal advice — attorney review required" banner, entity cards with risk badges, confidence, rationale, expandable real citations).

## Deployment

Single Cloud Run service (backend serves the Jinja2 frontend too). Secrets via `gcloud run deploy --update-secrets=GOOGLE_API_KEY=...,PARALLEL_API_KEY=...` — never env-vars or hardcoded. Firestore Native mode same project, Cloud Run service account gets `roles/datastore.user`. Set `min-instances=1` right before recording the demo video to avoid cold start.

## Cut from v1 (YAGNI) vs. must keep

**Cut**: auth/accounts (reports reachable via unguessable UUID URL only — documented as a demo-grade tradeoff), multi-tenancy, rate-limiting middleware, generic retry framework, `.fdx` parsing, token-level streaming, cross-report entity caching, Cloud Storage, job queue infra.

**Must keep (trust boundary / security — not optional)**: file upload validation (content-type allowlist, size cap ~25MB, reject empty) before bytes reach Gemini; API keys only via Secret Manager in deployment, `.env` gitignored; no script text or keys in logs; the citation-grounding filter; disclaimer + attorney-review flag rendered on every report.

## Build order (vertical slice first, no frontend/deploy until step 10)

1. Scaffold repo: LICENSE (MIT), requirements.txt, Dockerfile skeleton, `.env.example`, `.gitignore`, `main.py` health check. Smoke-test `google-adk`/`google-genai`/`parallel-web` imports + API keys.
2. `schemas.py` — lock `Entity`/`SearchCitation`/`RiskAssessment`/`Report`.
3. `ExtractorAgent` standalone against one real public-domain screenplay PDF; iterate prompt until extraction is clean (run as `python -m backend.agents.extractor`, no FastAPI yet).
4. `tools.py` `research_entity_web` standalone against 1-2 known entities; confirm result/excerpt shape.
5. `ResearcherAssessorAgent` end-to-end on one hardcoded entity; validate risk_tier/confidence output and the citation-filter logic.
6. Fan out over all entities from step 3.
7. `ReportSynthesizerAgent`, wire everything into a single pipeline. **Vertical-slice milestone: script-in → `Report`-out runnable from a CLI script.**
8. Wrap in `main.py`: `POST /api/analyze` (background task + Firestore save), `GET /api/reports/{id}`.
9. Add SSE progress (`progress.py` + `/stream` route).
10. Build the three Jinja2/HTMX/Tailwind screens.
11. Dockerize, deploy to Cloud Run, wire Secret Manager, smoke-test the deployed URL with a real upload.
12. Polish: README run instructions, sample scripts for judges, error/empty states, mobile pass.

## Verification

- Steps 3-7 are self-verifying via `python -m` CLI runs against real inputs (one public-domain screenplay, e.g. a Creative Commons script or a short original test script) — confirm the printed `Report` has real entities, real Parallel-sourced citations (spot-check a URL actually resolves and is relevant), and no citation outside the captured search results.
- After step 9: run the FastAPI app locally (`uvicorn backend.main:app --reload`), upload a script through `/`, confirm SSE progress events stream and the final report page renders.
- After step 11: hit the deployed Cloud Run URL directly, repeat the same upload-to-report flow, confirm Secret Manager-sourced keys work (no keys in Cloud Run env vars).
- Before submission: confirm `google-adk`/`google-genai`/`google-cloud-aiplatform` and `parallel-web` are genuinely imported and called in `backend/agents/*.py` (not just in requirements.txt), and that the LICENSE file renders in the GitHub repo's "About" section.

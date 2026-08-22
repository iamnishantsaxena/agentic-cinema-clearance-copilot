# Clearance Copilot

An AI agent that reads a screenplay and produces a cited legal/rights clearance risk memo — flagging real people, trademarks, songs, quotes, "based on true events" claims, and real locations that need clearance before production — so indie filmmakers get a credible first-pass risk report without paying $5-15k to outside clearance counsel.

Built for the **Google Cloud Agentic Cinema Hackathon** (Parallel partner track).

> **Not legal advice.** This is an automated first-pass analysis. Every report includes a disclaimer and flags items requiring attorney review.

## How it works

1. **Extract** — Gemini reads the screenplay and identifies every entity that could create clearance risk.
2. **Research** — for each entity, an agent searches the live web via [Parallel's Search API](https://parallel.ai) for its *current* legal status (trademark registration, active litigation, right-of-publicity exposure, recent news) — this can't come from a static knowledge cutoff, since clearance status changes over time.
3. **Assess** — each entity gets a risk tier (low/medium/high/critical), a confidence level, and a rationale, with citations filtered so the agent can never cite a URL that wasn't actually returned by search.
4. **Synthesize** — an executive summary and overall risk tier roll everything up into one report.

## Tech stack

- **Agents**: [Google ADK](https://google.github.io/adk-docs/) (`google-adk`) + Gemini (`google-genai`)
- **Search**: [Parallel](https://parallel.ai) Search API (`parallel-web`)
- **Backend**: FastAPI
- **Storage**: Firestore
- **Deployment**: Cloud Run

See [CLAUDE.md](CLAUDE.md) for the full architecture writeup and [docs/PLAN.md](docs/PLAN.md) for the original design doc.

## Running locally

Requires Python 3.12+.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then fill in .env:
#   GOOGLE_API_KEY   — https://aistudio.google.com/apikey
#   PARALLEL_API_KEY — https://platform.parallel.ai

# test entity extraction alone
python -m backend.agents.extractor samples/sample_script.txt

# run the full pipeline end-to-end (prints a Report as JSON)
python -m backend.agents.pipeline samples/sample_script.txt
```

## Sample scripts

- `samples/sample_script.txt` — high-risk: real person, trademark, real location, a song, a misattributed quote, a "based on true events" claim.
- `samples/sample_script_clean.txt` — low-risk: fully fictional names, places, and events, to show the report doesn't just flag everything.

## License

MIT — see [LICENSE](LICENSE).

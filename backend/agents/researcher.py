from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from backend.agents.tools import make_research_tool
from backend.schemas import Entity, RiskAssessment

RESEARCHER_INSTRUCTION = """\
You are a film production clearance researcher. You will be given one entity \
extracted from a screenplay (a real person, trademark/brand, song, quote, \
"based on true events" claim, or real location) along with its script context.

Use the research_entity_web tool to find its CURRENT real-world legal/clearance \
status — trademark registration, active litigation, right-of-publicity concerns \
for real people, copyright/licensing status for songs and quotes, and any recent \
news that would affect clearance. Run at least one search before assessing risk; \
you may search again if the first results are inconclusive.

Then produce a RiskAssessment:
- risk_tier: "low" (generic/public-domain/no real conflict), "medium" (some risk,
  likely clearable with standard licensing or disclaimers), "high" (real
  litigation/trademark conflict or right-of-publicity exposure), or "critical"
  (near-certain legal exposure if used unchanged)
- confidence: how confident you are given what the search actually returned
- rationale: 2-4 sentences explaining the tier, referencing what you found
- citations: only URLs, titles, and excerpts that your search tool actually
  returned — never invent or guess a citation
- attorney_review_required: true for any medium/high/critical tier, or any
  low-confidence assessment
"""


def build_researcher_agent(seen_urls: set[str]) -> LlmAgent:
    return LlmAgent(
        name="researcher_assessor",
        model="gemini-3.1-flash-lite",
        instruction=RESEARCHER_INSTRUCTION,
        tools=[make_research_tool(seen_urls)],
        output_schema=RiskAssessment,
        output_key="assessment",
    )


async def assess_entity(entity: Entity) -> RiskAssessment:
    seen_urls: set[str] = set()
    agent = build_researcher_agent(seen_urls)

    session_service = InMemorySessionService()
    runner = Runner(app_name="clearance-copilot", agent=agent, session_service=session_service)
    session = await session_service.create_session(app_name="clearance-copilot", user_id="pipeline")

    message = types.Content(
        role="user",
        parts=[types.Part(text=entity.model_dump_json())],
    )
    async for event in runner.run_async(user_id="pipeline", session_id=session.id, new_message=message):
        pass

    final_session = await session_service.get_session(
        app_name="clearance-copilot", user_id="pipeline", session_id=session.id
    )
    assessment = RiskAssessment.model_validate(final_session.state["assessment"])
    assessment.entity_id = entity.id
    assessment.entity_name = entity.name
    assessment.entity_type = entity.entity_type
    assessment.citations = [c for c in assessment.citations if c.url in seen_urls]
    return assessment


if __name__ == "__main__":
    import asyncio

    async def main():
        entity = Entity(
            id="e1",
            name="Bridge Over Troubled Water",
            entity_type="song_music",
            script_context='Joey hums a few bars of "Bridge Over Troubled Water," off-key.',
            page_or_scene_ref="INT. DINER - TIMES SQUARE - NIGHT",
        )
        assessment = await assess_entity(entity)
        print(assessment.model_dump_json(indent=2))

    asyncio.run(main())

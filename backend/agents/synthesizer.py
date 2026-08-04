from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from backend.schemas import ReportSummary, RiskAssessment

SYNTHESIZER_INSTRUCTION = """\
You are a film production clearance analyst writing the executive summary of a \
clearance risk report. You will be given a JSON list of per-entity risk \
assessments already completed by researchers.

Produce:
- overall_risk_tier: the single highest risk_tier present across all entities
  ("critical" > "high" > "medium" > "low"), unless there are so many
  medium-risk entities that the combined exposure warrants bumping it up —
  explain that judgment call in the summary if you do.
- executive_summary: 3-6 sentences a producer can read in 30 seconds — lead
  with the overall picture, then flag the specific entities that need
  attorney review and why. Do not restate every entity individually.
"""

synthesizer_agent = LlmAgent(
    name="synthesizer",
    model="gemini-2.5-flash",
    instruction=SYNTHESIZER_INSTRUCTION,
    output_schema=ReportSummary,
    output_key="summary",
)


async def synthesize_report(assessments: list[RiskAssessment]) -> ReportSummary:
    session_service = InMemorySessionService()
    runner = Runner(app_name="clearance-copilot", agent=synthesizer_agent, session_service=session_service)
    session = await session_service.create_session(app_name="clearance-copilot", user_id="pipeline")

    payload = [a.model_dump(mode="json") for a in assessments]
    message = types.Content(role="user", parts=[types.Part(text=str(payload))])
    async for event in runner.run_async(user_id="pipeline", session_id=session.id, new_message=message):
        pass

    final_session = await session_service.get_session(
        app_name="clearance-copilot", user_id="pipeline", session_id=session.id
    )
    return ReportSummary.model_validate(final_session.state["summary"])

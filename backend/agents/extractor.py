from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import backend.config  # noqa: F401  ensures .env is loaded regardless of entrypoint
from backend.schemas import EntityList

EXTRACTOR_INSTRUCTION = """\
You are a script clearance analyst. Read the screenplay text given to you and \
extract every entity that could create a legal clearance risk for production.

Use screenplay formatting conventions (ALL-CAPS character cues, scene headers \
like INT./EXT., parentheticals) to understand context, not just raw text.

Extract entities of these types only:
- real_person: any real, identifiable person named or clearly referenced
  (celebrities, public figures, or anyone described specifically enough to be
  identifiable)
- trademark_brand: real company/product/brand names
- song_music: any real song, lyric, or piece of music referenced or performed
- direct_quote: any line that reads as a quotation of an existing work, saying,
  or famous line (not original dialogue)
- true_events_claim: any "based on a true story" / "inspired by real events"
  style claim, or a scene depicting a specific real historical event
- real_location: specific, real, identifiable locations (not generic settings
  like "a diner" — only named real places)

For each entity, capture: a short name/label, its type, the surrounding script \
context (quote the relevant line(s)), and a page or scene reference (use the \
scene heading or a short locator if no page numbers are present).

If the script contains no entities of a given type, simply omit that type. \
Do not invent entities that aren't actually present in the text.
"""

extractor_agent = LlmAgent(
    name="extractor",
    model="gemini-3.1-flash-lite",
    instruction=EXTRACTOR_INSTRUCTION,
    output_schema=EntityList,
    output_key="entities",
)


async def extract_entities(script_text: str) -> EntityList:
    session_service = InMemorySessionService()
    runner = Runner(app_name="clearance-copilot", agent=extractor_agent, session_service=session_service)
    session = await session_service.create_session(app_name="clearance-copilot", user_id="pipeline")

    message = types.Content(role="user", parts=[types.Part(text=script_text)])
    async for event in runner.run_async(user_id="pipeline", session_id=session.id, new_message=message):
        pass

    final_session = await session_service.get_session(
        app_name="clearance-copilot", user_id="pipeline", session_id=session.id
    )
    return EntityList.model_validate(final_session.state["entities"])


if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path

    async def main():
        script_path = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/sample_script.txt")
        entities = await extract_entities(script_path.read_text())
        print(f"Extracted {len(entities.entities)} entities:")
        for e in entities.entities:
            print(f"  [{e.entity_type}] {e.name} — {e.page_or_scene_ref}")

    asyncio.run(main())

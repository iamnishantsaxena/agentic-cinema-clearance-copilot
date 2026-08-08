import asyncio
import uuid

from backend.agents.extractor import extract_entities
from backend.agents.researcher import assess_entity
from backend.agents.synthesizer import synthesize_report
from backend.schemas import Report

MAX_CONCURRENT_RESEARCH = 5


async def analyze_script(
    script_text: str | None,
    script_title: str,
    *,
    pdf_bytes: bytes | None = None,
    report_id: str | None = None,
) -> Report:
    entities = (await extract_entities(script_text, pdf_bytes=pdf_bytes)).entities

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_RESEARCH)

    async def assess_with_limit(entity):
        async with semaphore:
            return await assess_entity(entity)

    assessments = await asyncio.gather(*(assess_with_limit(e) for e in entities))

    summary = await synthesize_report(list(assessments))

    return Report(
        report_id=report_id or str(uuid.uuid4()),
        script_title=script_title,
        overall_risk_tier=summary.overall_risk_tier,
        executive_summary=summary.executive_summary,
        entity_assessments=list(assessments),
    )


if __name__ == "__main__":
    import sys
    from pathlib import Path

    async def main():
        script_path = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/sample_script.txt")
        report = await analyze_script(script_path.read_text(), script_path.stem)
        print(report.model_dump_json(indent=2))

    asyncio.run(main())

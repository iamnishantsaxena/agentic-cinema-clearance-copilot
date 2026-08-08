from functools import lru_cache

from google.cloud import firestore

from backend.config import GOOGLE_CLOUD_PROJECT
from backend.schemas import Report

COLLECTION = "reports"


@lru_cache(maxsize=1)
def _get_client() -> firestore.AsyncClient:
    return firestore.AsyncClient(project=GOOGLE_CLOUD_PROJECT or None)


async def save_report(report: Report) -> None:
    await _get_client().collection(COLLECTION).document(report.report_id).set(report.model_dump())


async def get_report(report_id: str) -> Report | None:
    snapshot = await _get_client().collection(COLLECTION).document(report_id).get()
    if not snapshot.exists:
        return None
    return Report.model_validate(snapshot.to_dict())


async def list_reports(limit: int = 50) -> list[Report]:
    query = (
        _get_client()
        .collection(COLLECTION)
        .order_by("generated_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [Report.model_validate(doc.to_dict()) async for doc in query.stream()]

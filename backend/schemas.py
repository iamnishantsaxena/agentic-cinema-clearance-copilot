from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

EntityType = Literal[
    "real_person",
    "trademark_brand",
    "song_music",
    "direct_quote",
    "true_events_claim",
    "real_location",
]

RiskTier = Literal["low", "medium", "high", "critical"]
Confidence = Literal["low", "medium", "high"]

DISCLAIMER = (
    "This report is an automated first-pass analysis, not legal advice. "
    "It does not constitute a clearance opinion and must not be relied on "
    "for production insurance (E&O) purposes without review by a qualified "
    "entertainment attorney."
)


class Entity(BaseModel):
    id: str
    name: str
    entity_type: EntityType
    script_context: str
    page_or_scene_ref: str


class EntityList(BaseModel):
    entities: list[Entity]


class SearchCitation(BaseModel):
    url: str
    title: str | None = None
    publish_date: str | None = None
    excerpt: str


class RiskAssessment(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: EntityType
    risk_tier: RiskTier
    confidence: Confidence
    rationale: str
    citations: list[SearchCitation] = Field(default_factory=list)
    attorney_review_required: bool
    last_checked: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ReportSummary(BaseModel):
    overall_risk_tier: RiskTier
    executive_summary: str


class Report(BaseModel):
    report_id: str
    script_title: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    overall_risk_tier: RiskTier
    executive_summary: str
    entity_assessments: list[RiskAssessment]
    disclaimer: str = DISCLAIMER

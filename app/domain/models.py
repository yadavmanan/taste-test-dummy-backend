"""Domain entities. No imports from other app layers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class StudyStatus(str, Enum):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    RETRIEVING = "RETRIEVING"
    ANALYSING = "ANALYSING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


Mode = Literal["live", "fixture"]


class Concept(BaseModel):
    id: str
    name: str
    description: str


class LaunchBrief(BaseModel):
    product_name: str
    category: str
    description: str = ""
    audience: str
    objective: str
    decision: str = ""
    markets: list[str] = Field(min_length=1, max_length=2)
    concepts: list[Concept] = Field(min_length=2, max_length=3)
    constraints: str = ""
    reference_points: list[str] = Field(default_factory=list)


class SignalCandidate(BaseModel):
    kind: Literal["entity", "tag"]
    id: str
    name: str
    type: str = ""
    parents: list[str] = Field(default_factory=list)
    description: str = ""
    selected: bool = False


class ConceptSeeds(BaseModel):
    concept_id: str
    hypothesis: str
    entity_queries: list[str] = Field(default_factory=list)
    tag_queries: list[str] = Field(default_factory=list)
    entity_candidates: list[SignalCandidate] = Field(default_factory=list)
    tag_candidates: list[SignalCandidate] = Field(default_factory=list)
    ambiguous: list[str] = Field(default_factory=list)


class PlannedQuery(BaseModel):
    concept_id: str
    market: Optional[str] = None
    output_type: str
    purpose: str


class ResearchPlan(BaseModel):
    decision_question: str
    concept_seeds: list[ConceptSeeds]
    qloo_cannot_answer: list[str] = Field(default_factory=list)
    queries: list[PlannedQuery] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    entity_id: str
    name: str
    type: str = ""
    affinity: Optional[float] = None
    popularity: Optional[float] = None
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    explained_by: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    id: str
    source: Literal["qloo"] = "qloo"
    mode: Mode
    concept_id: str
    market: Optional[str] = None
    purpose: str
    output_type: str
    input_entities: list[dict] = Field(default_factory=list)
    input_tags: list[dict] = Field(default_factory=list)
    location_context: Optional[str] = None
    retrieved_at: str = Field(default_factory=now_iso)
    status: Literal["ok", "empty", "error"] = "ok"
    error: Optional[str] = None
    items: list[EvidenceItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    statement: str
    kind: Literal["evidence", "inference", "hypothesis"] = "inference"
    evidence_ids: list[str] = Field(default_factory=list)
    flag: Optional[str] = None


class ConceptAssessment(BaseModel):
    concept_id: str
    aligned: list[Finding] = Field(default_factory=list)
    mismatches: list[Finding] = Field(default_factory=list)
    distinctive: list[Finding] = Field(default_factory=list)
    localisation_question: str = ""
    evidence_gaps: list[str] = Field(default_factory=list)
    alternative_direction: str = ""
    confidence: Literal["low", "medium", "high"] = "low"
    confidence_rationale: str = ""


class ConceptProfile(BaseModel):
    """Deterministic, evidence-derived comparison data. Not a Qloo metric."""
    concept_id: str
    calls_ok: int = 0
    calls_failed: int = 0
    calls_empty: int = 0
    item_count: int = 0
    domains: list[str] = Field(default_factory=list)
    top_tags: list[dict] = Field(default_factory=list)
    distinctive_tags: list[str] = Field(default_factory=list)
    shared_tags: list[str] = Field(default_factory=list)
    market_overlap: list[dict] = Field(default_factory=list)
    coverage_label: Literal["thin", "moderate", "broad"] = "thin"


class Experiment(BaseModel):
    id: str
    title: str
    hypothesis: str
    audience: str = ""
    variable: str = ""
    method: str = ""
    primary_metric: str = ""
    guardrail: str = ""
    decision_informed: str = ""
    effort: Literal["low", "medium", "high"] = "medium"
    priority: int = 1
    result_that_changes_recommendation: str = ""
    concept_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Baseline(BaseModel):
    label: str = "LLM-only baseline (no Qloo evidence)"
    summary: str = ""
    concept_views: list[dict] = Field(default_factory=list)
    recommended_next_step: str = ""
    audit: dict = Field(default_factory=dict)


class TimelineEvent(BaseModel):
    ts: str = Field(default_factory=now_iso)
    stage: str
    message: str
    level: Literal["info", "warn", "error"] = "info"
    evidence_id: Optional[str] = None


class SkillUse(BaseModel):
    stage: str
    skill: str
    purpose: str
    ts: str = Field(default_factory=now_iso)


class Study(BaseModel):
    id: str
    status: StudyStatus = StudyStatus.DRAFT
    mode: Mode = "live"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    brief: LaunchBrief
    plan: Optional[ResearchPlan] = None
    evidence: list[Evidence] = Field(default_factory=list)
    profiles: list[ConceptProfile] = Field(default_factory=list)
    assessments: list[ConceptAssessment] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    executive_summary: str = ""
    recommendation: str = ""
    open_questions: list[str] = Field(default_factory=list)
    baseline: Optional[Baseline] = None
    report_markdown: str = ""
    timeline: list[TimelineEvent] = Field(default_factory=list)
    skills_used: list[SkillUse] = Field(default_factory=list)
    error: Optional[str] = None
    qloo_calls_used: int = 0

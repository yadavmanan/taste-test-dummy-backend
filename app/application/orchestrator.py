from __future__ import annotations

import asyncio
from typing import Optional

from ..config import Settings
from ..domain.models import (LaunchBrief, SignalCandidate, Study, StudyStatus, TimelineEvent, new_id)
from ..domain.ports import LLMPort, QlooPort, SkillPort, StudyRepository
from .analysis import AnalysisService, build_profiles
from .evidence import EvidenceService
from .planning import PlanningService
from .report import build_report
from .skill_runner import SkillRunner


class WorkflowError(Exception):
    pass


EDITABLE = (StudyStatus.AWAITING_CONFIRMATION, StudyStatus.FAILED, StudyStatus.COMPLETE)


class StudyOrchestrator:
    """DRAFT -> PLAN -> RESOLVE -> CONFIRM -> RETRIEVE -> COMPARE -> STRESS_TEST -> EXPERIMENTS -> REPORT."""

    def __init__(self, repo: StudyRepository, qloo_live: Optional[QlooPort], qloo_fixture: QlooPort,
                 skills: SkillPort, llm: LLMPort, settings: Settings):
        self.repo, self.settings = repo, settings
        self.qloo = {"live": qloo_live, "fixture": qloo_fixture}
        runner = SkillRunner(skills)
        self.planning = PlanningService(runner)
        self.evidence = EvidenceService()
        self.analysis = AnalysisService(runner, llm)
        self._tasks: set[asyncio.Task] = set()

    def recover_interrupted(self) -> None:
        for s in self.repo.list():
            if s.status in (StudyStatus.PLANNING, StudyStatus.RETRIEVING, StudyStatus.ANALYSING):
                s.status, s.error = StudyStatus.FAILED, "Interrupted by server restart"
                self.repo.save(s)

    def _emit(self, study: Study):
        def emit(stage: str, message: str, level: str = "info", evidence_id: Optional[str] = None) -> None:
            study.timeline.append(TimelineEvent(stage=stage, message=message, level=level, evidence_id=evidence_id))
            self.repo.save(study)
        return emit

    def _get(self, study_id: str) -> Study:
        s = self.repo.get(study_id)
        if not s:
            raise WorkflowError("Study not found")
        return s

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    def create(self, brief: LaunchBrief, mode: str) -> Study:
        if mode == "live" and not self.qloo["live"]:
            raise WorkflowError("Live mode is unavailable: Qloo credentials are not configured")
        ids = [c.id for c in brief.concepts]
        if len(set(ids)) != len(ids):
            raise WorkflowError("Concept ids must be unique")
        study = Study(id=new_id("st"), mode=mode, brief=brief)  # type: ignore[arg-type]
        self.repo.save(study)
        return study

    def start_planning(self, study_id: str) -> Study:
        study = self._get(study_id)
        if study.status not in (StudyStatus.DRAFT, StudyStatus.FAILED, StudyStatus.AWAITING_CONFIRMATION):
            raise WorkflowError(f"Cannot plan from status {study.status.value}")
        study.status, study.error = StudyStatus.PLANNING, None
        self.repo.save(study)
        self._spawn(self._plan(study))
        return study

    async def _plan(self, study: Study) -> None:
        emit = self._emit(study)
        try:
            study.plan = await self.planning.build_plan(study, self.qloo[study.mode], emit)
            study.status = StudyStatus.AWAITING_CONFIRMATION
            emit("plan", "Research plan ready. Review and confirm the resolved signals.")
        except Exception as exc:
            study.status, study.error = StudyStatus.FAILED, f"Planning failed: {exc}"
            emit("plan", study.error, level="error")

    def update_inputs(self, study_id: str, seeds: list[dict]) -> Study:
        study = self._get(study_id)
        if study.status not in EDITABLE or not study.plan:
            raise WorkflowError("Inputs can only be edited before a run")
        by_id = {s.concept_id: s for s in study.plan.concept_seeds}
        for incoming in seeds:
            tgt = by_id.get(incoming.get("concept_id"))
            if not tgt:
                continue
            tgt.entity_candidates = [SignalCandidate(**c) for c in incoming.get("entity_candidates", [])]
            tgt.tag_candidates = [SignalCandidate(**c) for c in incoming.get("tag_candidates", [])]
            tgt.ambiguous = [] if any(c.selected for c in tgt.entity_candidates) else tgt.ambiguous
        self.repo.save(study)
        return study

    def start_run(self, study_id: str) -> Study:
        study = self._get(study_id)
        if study.status not in EDITABLE or not study.plan:
            raise WorkflowError("Study must have a confirmed research plan")
        for s in study.plan.concept_seeds:
            if not any(c.selected for c in s.entity_candidates) and not any(c.selected for c in s.tag_candidates):
                raise WorkflowError(f"Select at least one entity or tag for concept '{s.concept_id}'")
        study.status, study.error = StudyStatus.RETRIEVING, None
        study.evidence, study.assessments, study.experiments, study.profiles = [], [], [], []
        study.baseline, study.report_markdown = None, ""
        self.repo.save(study)
        self._spawn(self._run(study))
        return study

    async def _run(self, study: Study) -> None:
        emit = self._emit(study)
        baseline_task = asyncio.create_task(self.analysis.baseline(study, emit))
        try:
            emit("retrieve", f"Retrieving evidence from Qloo ({study.mode} mode)")
            await self.evidence.retrieve(study, self.qloo[study.mode], self.settings.qloo_call_budget, emit)
            if not any(e.status == "ok" for e in study.evidence):
                raise WorkflowError("Qloo returned no usable evidence; adjust the seed signals and retry")

            study.status = StudyStatus.ANALYSING
            emit("compare", "Comparing concepts on a consistent evidence basis")
            study.profiles = build_profiles(study)
            self.repo.save(study)

            await self.analysis.stress_test(study, emit)
            await self.analysis.grounding_audit(study, emit)
            await self.analysis.synthesise(study, emit)
            await self.analysis.plan_experiments(study, emit)
            await baseline_task
            study.report_markdown = build_report(study)
            study.status = StudyStatus.COMPLETE
            emit("report", "Report ready")
        except Exception as exc:
            study.status, study.error = StudyStatus.FAILED, str(exc)
            if not baseline_task.done():
                baseline_task.cancel()
            if study.evidence:
                study.report_markdown = build_report(study)
            emit("error", f"Run failed: {exc}", level="error")

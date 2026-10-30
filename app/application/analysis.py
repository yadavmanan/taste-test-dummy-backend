from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from typing import Callable, Optional

from ..domain.models import (Baseline, ConceptAssessment, ConceptProfile, Evidence, Experiment, Finding, Study)
from ..domain.ports import LLMPort
from .planning import PLACE
from .skill_runner import SkillRunner

_RISKY = re.compile(
    r"\b(will (?:increase|boost|drive|win|outsell)|guarantee[sd]?|proves?|proven|predicts?|predicted|"
    r"definitely|certainly|purchase intent|sales lift|conversion rate)\b", re.I)


def lint(text: str) -> Optional[str]:
    for m in _RISKY.finditer(text or ""):
        before = text[max(0, m.start() - 30): m.start()].lower()
        if re.search(r"\b(not|no|nor|never|cannot|doesn't|does not|isn't|without)\b", before):
            continue
        return f"Language check: '{m.group(0)}' may overstate what the evidence shows"
    return None


STRESS_TASK = """Stress-test ONE launch concept using ONLY the Qloo evidence digest provided (evidence ids like ev_03).
Rules:
- A finding of kind "evidence" must cite one or more evidence_ids from the digest and describe only what returned items/tags show. Prefer phrasing such as "the retrieved evidence suggests".
- Use kind "inference" for your interpretation of cited evidence, and "hypothesis" for anything not directly supported (no ids needed).
- Never claim purchase intent, sales lift, causality or that Qloo proves anything. Never invent scores, sample sizes, or entities that are not in the digest.
- Raw affinity values from different queries or output types are not comparable; do not rank concepts by them.
- Only 'place' evidence is market-specific; other output types apply to all markets.
- Challenge at least one assumption embedded in the concept. If evidence is thin, empty or failed, say so under evidence_gaps instead of forcing alignment.
Return JSON:
{"aligned":[F],"mismatches":[F],"distinctive":[F],"localisation_question":"...","evidence_gaps":["..."],
 "alternative_direction":"a testable revision, not a guaranteed improvement",
 "confidence":"low|medium|high","confidence_rationale":"based on coverage and quality of evidence only"}
where F = {"statement":"...","kind":"evidence|inference|hypothesis","evidence_ids":["ev_01"]}. Give 2-4 findings per list."""

AUDIT_TASK = """Audit these findings before they are shown to a decision maker. Findings are keyed (e.g. "c1.aligned.0").
For each finding of kind "evidence", verify that the cited evidence ids exist in the digest AND that the statement is supported by the items/tags actually listed there.
Return JSON: {"verdicts":[{"key":"c1.aligned.0","supported":true,"reason":"short reason"}]} with exactly one verdict per finding of kind "evidence". Set supported=false ONLY if a cited id is missing, or the statement claims something the listed items/tags do not show. Do not rewrite findings."""

SYNTH_TASK = """Write the decision summary for a launch study.
Return JSON: {"executive_summary":"3-5 sentences: what the evidence suggests, the main trade-off, and the key uncertainty",
"recommendation":"which hypothesis or question deserves validation first and why; bounded language, do not declare a winner or predict sales",
"open_questions":["3-5 unresolved questions"]}
Base every statement on the assessments and profiles provided. Clearly separate evidence from interpretation.
Prioritise by the value of the uncertainty to be resolved, not by which concept has "stronger" alignment: raw evidence from different queries is not comparable."""

REPORT_EDIT_TASK = """Edit the executive_summary and recommendation for clarity and plain, direct voice. Remove filler and hype.
Do NOT add facts, numbers or claims, and keep every caveat. Return JSON: {"executive_summary":"...","recommendation":"..."}"""

EXPERIMENT_TASK = """Create a prioritised validation plan (3-5 experiments) from the evidence gaps, mismatches and open questions.
Each experiment must target a specific uncertainty. Do not invent benchmark thresholds; say the team must set the threshold before the test runs.
Return JSON: {"experiments":[{"title":"","hypothesis":"","audience":"recruitment approach","variable":"what is isolated",
"method":"e.g. concept test, message test, landing-page test, interviews, small paid-media test","primary_metric":"","guardrail":"",
"decision_informed":"","effort":"low|medium|high","priority":1,"result_that_changes_recommendation":"",
"concept_ids":["c1"],"evidence_ids":["ev_01"]}]}
Priority 1 is highest. Order the list by priority."""

BASELINE_SYSTEM = ("You are a senior brand strategist. Answer from general knowledge only; you have no access to any "
                   "external cultural data. Be concise.")
BASELINE_TASK = """Given this launch brief, assess each concept and recommend what to do next.
Return JSON: {"summary":"3-4 sentences","concept_views":[{"concept_id":"","view":"2-3 sentences on cultural fit for this audience and markets","assumptions":["key assumptions"]}],
"recommended_next_step":"one sentence"}"""


def evidence_digest(evs: list[Evidence], top: int = 8) -> list[dict]:
    out = []
    for e in evs:
        out.append({
            "id": e.id, "concept_id": e.concept_id, "purpose": e.purpose, "output_type": e.output_type,
            "market": e.market, "status": e.status, "error": e.error,
            "input_entities": [x["name"] for x in e.input_entities],
            "input_tags": [x["name"] for x in e.input_tags],
            "items": [{"name": i.name, "affinity": i.affinity, "tags": i.tags[:5]} for i in e.items[:top]],
        })
    return out


def build_profiles(study: Study) -> list[ConceptProfile]:
    tags_by_concept: dict[str, Counter] = {}
    profiles: dict[str, ConceptProfile] = {}
    for c in study.brief.concepts:
        evs = [e for e in study.evidence if e.concept_id == c.id]
        cnt: Counter = Counter()
        for e in evs:
            for it in e.items:
                for t in it.tags:
                    cnt[t.strip().lower()] += 1
        tags_by_concept[c.id] = cnt
        ok = [e for e in evs if e.status == "ok"]
        items = sum(len(e.items) for e in ok)
        domains = sorted({e.output_type.split(":")[-1] for e in ok})
        label = "broad" if len(ok) >= 4 and items >= 25 and len(domains) >= 3 else "moderate" if len(ok) >= 3 else "thin"
        p = ConceptProfile(
            concept_id=c.id, calls_ok=len(ok), calls_failed=sum(e.status == "error" for e in evs),
            calls_empty=sum(e.status == "empty" for e in evs), item_count=items, domains=domains,
            top_tags=[{"tag": t, "count": n} for t, n in cnt.most_common(8)], coverage_label=label,
        )
        markets = study.brief.markets
        if len(markets) == 2:
            by_m = {m: {i.name for e in ok if e.output_type == PLACE and e.market == m for i in e.items} for m in markets}
            a, b = by_m[markets[0]], by_m[markets[1]]
            if a or b:
                p.market_overlap = [{"markets": markets, "shared": sorted(a & b)[:6],
                                     "only_first": sorted(a - b)[:6], "only_second": sorted(b - a)[:6]}]
        profiles[c.id] = p
    for cid, p in profiles.items():
        others = [set(c) for k, c in tags_by_concept.items() if k != cid]
        mine = tags_by_concept[cid]
        p.distinctive_tags = [t for t, _ in mine.most_common() if all(t not in o for o in others)][:6]
        p.shared_tags = [t for t, _ in mine.most_common() if others and all(t in o for o in others)][:6]
    return list(profiles.values())


class AnalysisService:
    def __init__(self, skills: SkillRunner, llm: LLMPort):
        self.skills = skills
        self.llm = llm

    async def stress_test(self, study: Study, emit: Callable) -> None:
        profiles = {p.concept_id: p for p in study.profiles}
        brief = study.brief.model_dump(exclude={"concepts"})
        valid_ids = {e.id for e in study.evidence}

        async def one(concept) -> ConceptAssessment:
            seeds = next((s for s in study.plan.concept_seeds if s.concept_id == concept.id), None)
            payload = {
                "brief": brief, "concept": concept.model_dump(), "hypothesis": seeds.hypothesis if seeds else "",
                "evidence": evidence_digest([e for e in study.evidence if e.concept_id == concept.id]),
                "this_concept_profile": profiles[concept.id].model_dump(),
                "other_concepts_top_tags": {k: [t["tag"] for t in v.top_tags[:5]] for k, v in profiles.items() if k != concept.id},
            }
            raw = await self.skills.run(study, "stress_test", STRESS_TASK, payload)
            a = ConceptAssessment(concept_id=concept.id)
            for sec in ("aligned", "mismatches", "distinctive"):
                findings = []
                for f in raw.get(sec, []) or []:
                    if not isinstance(f, dict) or not f.get("statement"):
                        continue
                    ids = [i for i in (f.get("evidence_ids") or []) if i in valid_ids]
                    kind = f.get("kind") if f.get("kind") in ("evidence", "inference", "hypothesis") else "inference"
                    flag = None
                    if kind in ("evidence", "inference") and not ids:
                        kind, flag = "hypothesis", "Downgraded: no valid evidence reference"
                    findings.append(Finding(statement=str(f["statement"]), kind=kind, evidence_ids=ids,
                                            flag=flag or lint(str(f["statement"]))))
                setattr(a, sec, findings)
            a.localisation_question = str(raw.get("localisation_question") or "")
            a.evidence_gaps = [str(x) for x in raw.get("evidence_gaps", []) or []]
            a.alternative_direction = str(raw.get("alternative_direction") or "")
            conf = str(raw.get("confidence", "low")).lower()
            a.confidence = conf if conf in ("low", "medium", "high") else "low"
            if profiles[concept.id].coverage_label == "thin" and a.confidence != "low":
                a.confidence = "low"  # confidence may not exceed what evidence coverage supports
            a.confidence_rationale = str(raw.get("confidence_rationale") or "")
            emit("stress_test", f"Stress test complete for '{concept.name}'")
            return a

        emit("stress_test", "Stress-testing concepts against retrieved evidence")
        study.assessments = list(await asyncio.gather(*[one(c) for c in study.brief.concepts]))

    async def grounding_audit(self, study: Study, emit: Callable) -> None:
        keyed = {}
        for a in study.assessments:
            for sec in ("aligned", "mismatches", "distinctive"):
                for i, f in enumerate(getattr(a, sec)):
                    keyed[f"{a.concept_id}.{sec}.{i}"] = f
        payload = {
            "findings": {k: {"statement": f.statement, "kind": f.kind, "evidence_ids": f.evidence_ids} for k, f in keyed.items()},
            "evidence": evidence_digest(study.evidence),
        }
        emit("audit", "Auditing every finding against the evidence ledger")
        try:
            raw = await self.skills.run(study, "grounding_audit", AUDIT_TASK, payload)
        except Exception as exc:
            emit("audit", f"Audit step unavailable ({exc}); deterministic reference checks only", level="warn")
            return
        n = 0
        for u in raw.get("verdicts", []) or []:
            f = keyed.get(str(u.get("key")))
            if f and f.kind == "evidence" and u.get("supported") is False:
                f.kind, f.flag, n = "hypothesis", f"Audit: {str(u.get('reason', 'not supported by cited evidence'))[:160]}", n + 1
        emit("audit", f"Audit complete: {n} finding(s) downgraded to hypothesis" if n else "Audit complete: all evidence-labelled findings verified")

    async def synthesise(self, study: Study, emit: Callable) -> None:
        emit("synthesis", "Writing decision summary")
        payload = {
            "brief": study.brief.model_dump(),
            "assessments": [a.model_dump() for a in study.assessments],
            "profiles": [p.model_dump() for p in study.profiles],
        }
        raw = await self.llm.complete_json(
            "You are a pre-launch decision analyst. Use only the supplied assessments; never invent data.",
            f"{SYNTH_TASK}\n\n<data>\n{json.dumps(payload, default=str)}\n</data>")
        summary, rec = str(raw.get("executive_summary", "")), str(raw.get("recommendation", ""))
        study.open_questions = [str(q) for q in raw.get("open_questions", [])][:6]
        try:
            edited = await self.skills.run(study, "report", REPORT_EDIT_TASK, {"executive_summary": summary, "recommendation": rec})
            summary, rec = str(edited.get("executive_summary") or summary), str(edited.get("recommendation") or rec)
        except Exception as exc:
            emit("synthesis", f"Prose edit skipped: {exc}", level="warn")
        study.executive_summary, study.recommendation = summary, rec

    async def plan_experiments(self, study: Study, emit: Callable) -> None:
        emit("experiments", "Converting uncertainties into a validation plan")
        payload = {
            "brief": study.brief.model_dump(),
            "gaps_and_mismatches": [
                {"concept_id": a.concept_id, "mismatches": [f.statement for f in a.mismatches],
                 "evidence_gaps": a.evidence_gaps, "localisation_question": a.localisation_question,
                 "alternative_direction": a.alternative_direction, "confidence": a.confidence}
                for a in study.assessments],
            "open_questions": study.open_questions,
            "evidence_ids": [e.id for e in study.evidence],
        }
        raw = await self.skills.run(study, "experiments", EXPERIMENT_TASK, payload)
        cids = {c.id for c in study.brief.concepts}
        eids = {e.id for e in study.evidence}
        exps = []
        for i, x in enumerate(raw.get("experiments", []) or [], start=1):
            if not isinstance(x, dict) or not x.get("title"):
                continue
            effort = str(x.get("effort", "medium")).lower()
            try:
                prio = int(x.get("priority", i))
            except (TypeError, ValueError):
                prio = i
            exps.append(Experiment(
                id=f"exp_{i}", title=str(x["title"]), hypothesis=str(x.get("hypothesis", "")),
                audience=str(x.get("audience", "")), variable=str(x.get("variable", "")), method=str(x.get("method", "")),
                primary_metric=str(x.get("primary_metric", "")), guardrail=str(x.get("guardrail", "")),
                decision_informed=str(x.get("decision_informed", "")),
                effort=effort if effort in ("low", "medium", "high") else "medium", priority=prio,
                result_that_changes_recommendation=str(x.get("result_that_changes_recommendation", "")),
                concept_ids=[c for c in x.get("concept_ids", []) if c in cids],
                evidence_ids=[e for e in x.get("evidence_ids", []) if e in eids]))
        study.experiments = sorted(exps, key=lambda e: e.priority)

    async def baseline(self, study: Study, emit: Callable) -> None:
        try:
            raw = await self.llm.complete_json(
                BASELINE_SYSTEM, f"{BASELINE_TASK}\n\n<data>\n{study.brief.model_dump_json()}\n</data>")
        except Exception as exc:
            emit("baseline", f"Baseline failed: {exc}", level="warn")
            return
        views = [v for v in raw.get("concept_views", []) if isinstance(v, dict)]
        text = " ".join([str(raw.get("summary", ""))] + [str(v.get("view", "")) for v in views])
        study.baseline = Baseline(
            summary=str(raw.get("summary", "")), concept_views=views,
            recommended_next_step=str(raw.get("recommended_next_step", "")),
            audit={"evidence_references": 0, "qloo_items_used": 0, "named_experiments": 0,
                   "language_flag": lint(text)})
        emit("baseline", "LLM-only baseline generated from the same brief (no Qloo evidence)")

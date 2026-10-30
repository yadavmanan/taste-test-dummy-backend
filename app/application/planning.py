from __future__ import annotations

import asyncio
from typing import Callable

from ..domain.models import (ConceptSeeds, PlannedQuery, ResearchPlan, SignalCandidate, Study)
from ..domain.ports import QlooPort
from .skill_runner import SkillRunner

# Output types we ask Qloo for. Only "place" accepts a location filter.
OUTPUT_TYPES = [
    ("urn:entity:brand", "Adjacent brands culturally associated with the concept's signals"),
    ("urn:entity:artist", "Music taste associated with the concept's signals"),
    ("urn:entity:tv_show", "Screen and media taste associated with the concept's signals"),
]
PLACE = "urn:entity:place"

PLAN_TASK = """Build a research plan for this launch brief. Treat each concept as a falsifiable hypothesis, not a fact.
Return JSON:
{
 "decision_question": "one sentence",
 "concepts": [
   {"concept_id": "<id from brief>",
    "hypothesis": "falsifiable hypothesis about cultural fit of this concept for the audience and markets",
    "entity_queries": ["3-5 real cultural entities that embody this concept (brands, artists, TV shows, places, products). Bare official name only, like 'Blue Bottle Coffee' or 'Chef's Table': no descriptors, no parentheses, no generic categories. Include relevant brief reference points."],
    "tag_queries": ["2-4 short plain keywords for taste tags, e.g. 'coffee', 'outdoor dining', 'indie'"]}
 ],
 "qloo_cannot_answer": ["2-4 questions this evidence cannot answer, e.g. purchase intent, price sensitivity, causal lift"]
}
Use the concept ids exactly as given. Entities must be real and searchable by name."""


class PlanningService:
    def __init__(self, skills: SkillRunner):
        self.skills = skills

    async def build_plan(self, study: Study, qloo: QlooPort, emit: Callable) -> ResearchPlan:
        brief = study.brief
        emit("plan", "Decomposing the launch brief into hypotheses and seed signals")
        raw = await self.skills.run(study, "plan", PLAN_TASK, brief.model_dump())
        by_id = {c.get("concept_id"): c for c in raw.get("concepts", []) if isinstance(c, dict)}

        seeds: list[ConceptSeeds] = []
        for c in brief.concepts:
            r = by_id.get(c.id, {})
            seeds.append(
                ConceptSeeds(
                    concept_id=c.id,
                    hypothesis=str(r.get("hypothesis") or f"{c.name} is culturally aligned with the stated audience."),
                    entity_queries=[str(q) for q in (r.get("entity_queries") or [])][:5],
                    tag_queries=[str(q) for q in (r.get("tag_queries") or [])][:4],
                )
            )

        emit("resolve", "Resolving entities and tags against Qloo lookup endpoints")
        await asyncio.gather(*[self._resolve(s, qloo, study, emit) for s in seeds])

        queries: list[PlannedQuery] = []
        for s in seeds:
            for m in brief.markets:
                queries.append(PlannedQuery(concept_id=s.concept_id, market=m, output_type=PLACE,
                                            purpose=f"Local venues associated with the concept's signals in {m}"))
            for otype, purpose in OUTPUT_TYPES:
                queries.append(PlannedQuery(concept_id=s.concept_id, output_type=otype, purpose=purpose))

        return ResearchPlan(
            decision_question=str(raw.get("decision_question") or brief.decision or brief.objective),
            concept_seeds=seeds,
            qloo_cannot_answer=[str(x) for x in raw.get("qloo_cannot_answer", [])][:6]
            or ["Purchase intent", "Price sensitivity", "Causal impact of a campaign"],
            queries=queries,
        )

    async def _resolve(self, seeds: ConceptSeeds, qloo: QlooPort, study: Study, emit: Callable) -> None:
        async def ent(q: str):
            try:
                study.qloo_calls_used += 1
                return q, await qloo.search_entities(q, take=4), None
            except Exception as exc:
                return q, [], str(exc)

        async def tag(q: str):
            try:
                study.qloo_calls_used += 1
                return q, await qloo.search_tags(q, take=6), None
            except Exception as exc:
                return q, [], str(exc)

        ent_res, tag_res = await asyncio.gather(
            asyncio.gather(*[ent(q) for q in seeds.entity_queries]),
            asyncio.gather(*[tag(q) for q in seeds.tag_queries]),
        )

        seen: set[str] = set()
        for q, results, err in ent_res:
            if err:
                emit("resolve", f"Entity lookup failed for '{q}': {err}", level="warn")
                seeds.ambiguous.append(q)
                continue
            exact = [r for r in results if r["name"] and (r["name"].lower() in q.lower() or q.lower() in r["name"].lower())]
            if not any((r["name"] or "").lower() == q.lower() for r in results):
                seeds.ambiguous.append(q)
            for i, r in enumerate(results[:3]):
                if not r["entity_id"] or r["entity_id"] in seen:
                    continue
                seen.add(r["entity_id"])
                seeds.entity_candidates.append(
                    SignalCandidate(kind="entity", id=r["entity_id"], name=r["name"], type=r["type"],
                                    description=r.get("description") or "",
                                    selected=bool(exact) and r is exact[0])
                )

        for q, results, err in tag_res:
            if err:
                emit("resolve", f"Tag lookup failed for '{q}': {err}", level="warn")
                continue
            qwords = {w for w in q.lower().split() if len(w) > 2}
            picked = False
            for i, r in enumerate(results[:4]):
                if not r["id"] or r["id"] in seen:
                    continue
                seen.add(r["id"])
                match = bool(qwords & set((r["name"] or "").lower().split())) and not picked
                picked = picked or match
                seeds.tag_candidates.append(
                    SignalCandidate(kind="tag", id=r["id"], name=r["name"], type=r["type"],
                                    parents=[p for p in r.get("parents", []) if p],
                                    description=f"matched '{q}'", selected=match)
                )
        n_e = sum(c.selected for c in seeds.entity_candidates)
        n_t = sum(c.selected for c in seeds.tag_candidates)
        emit("resolve", f"{seeds.concept_id}: {n_e} entities and {n_t} tags pre-selected"
             + (f"; needs confirmation: {', '.join(seeds.ambiguous)}" if seeds.ambiguous else ""))

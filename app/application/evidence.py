from __future__ import annotations

import asyncio
from typing import Callable

from ..domain.models import Evidence, EvidenceItem, Study, now_iso
from ..domain.ports import QlooPort
from .planning import PLACE

TAKE = 8

BASE_LIMITS = [
    "Qloo affinity describes taste association, not purchase intent or causal lift.",
    "Results are not representative of every individual in the audience.",
]


def _limits(output_type: str, market: str | None) -> list[str]:
    if output_type == PLACE:
        return BASE_LIMITS + ["Location affinity is not foot traffic, market size or store performance."]
    return BASE_LIMITS + ["This output type has no market filter; the same result applies to all markets."]


class EvidenceService:
    async def retrieve(self, study: Study, qloo: QlooPort, budget: int, emit: Callable) -> None:
        assert study.plan
        seeds = {s.concept_id: s for s in study.plan.concept_seeds}
        specs = []
        for q in study.plan.queries:
            if q.concept_id not in seeds:
                continue
            specs.append(q)
        if len(specs) > budget:
            emit("retrieve", f"Call budget of {budget} reached; trimming {len(specs) - budget} planned queries", level="warn")
            specs = specs[:budget]

        evidences: list[Evidence] = []
        for i, q in enumerate(specs, start=1):
            s = seeds[q.concept_id]
            ents = [c for c in s.entity_candidates if c.selected]
            tags = [c for c in s.tag_candidates if c.selected and (not c.parents or q.output_type in c.parents)]
            evidences.append(
                Evidence(
                    id=f"ev_{i:02d}", mode=qloo.mode, concept_id=q.concept_id, market=q.market, purpose=q.purpose,
                    output_type=q.output_type,
                    input_entities=[{"id": c.id, "name": c.name} for c in ents],
                    input_tags=[{"id": c.id, "name": c.name} for c in tags],
                    location_context=q.market if q.output_type == PLACE else None,
                    limitations=_limits(q.output_type, q.market),
                )
            )
        study.evidence = evidences

        async def run(ev: Evidence) -> None:
            if not ev.input_entities and not ev.input_tags:
                ev.status, ev.error = "error", "No confirmed signals compatible with this output type"
                emit("retrieve", f"{ev.id} skipped: {ev.error}", level="warn", evidence_id=ev.id)
                return
            params: dict = {"filter.type": ev.output_type, "take": TAKE}
            if ev.input_entities:
                params["signal.interests.entities"] = ",".join(e["id"] for e in ev.input_entities)
            if ev.input_tags:
                params["signal.interests.tags"] = ",".join(t["id"] for t in ev.input_tags)
            if ev.location_context:
                params["filter.location.query"] = ev.location_context
            emit("retrieve", f"{ev.id}: {ev.purpose}", evidence_id=ev.id)
            try:
                study.qloo_calls_used += 1
                rows = await qloo.insights(params)
            except Exception as exc:
                ev.status, ev.error = "error", str(exc)[:300]
                emit("retrieve", f"{ev.id} failed: {ev.error}", level="error", evidence_id=ev.id)
                return
            ev.items = [EvidenceItem(**{k: r.get(k) for k in EvidenceItem.model_fields if r.get(k) is not None}) for r in rows]
            ev.status = "ok" if ev.items else "empty"
            ev.retrieved_at = now_iso()
            emit("retrieve", f"{ev.id}: {len(ev.items)} results returned" if ev.items else f"{ev.id}: no results (coverage gap)",
                 level="info" if ev.items else "warn", evidence_id=ev.id)

        await asyncio.gather(*[run(e) for e in evidences])

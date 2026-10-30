from __future__ import annotations

from ..domain.models import Study

CAVEAT = ("Qloo affinity is a taste-association signal. It is not purchase intent, market size, causal lift or a sales "
          "forecast. Findings labelled hypothesis have not been validated.")


def _src(study: Study) -> str:
    return "Live Qloo evidence" if study.mode == "live" else "ILLUSTRATIVE FIXTURE DATA - not live Qloo"


def build_report(study: Study) -> str:
    b = study.brief
    names = {c.id: c.name for c in b.concepts}
    L: list[str] = [f"# Cultural Fit Stress Test: {b.product_name}", "",
                    f"_Data source: {_src(study)}. Generated {study.updated_at}. Human review required before use as a business recommendation._", ""]
    L += ["## 1. Executive recommendation", "", study.executive_summary or "_Not available._", "",
          f"**Suggested validation priority:** {study.recommendation}", ""]
    L += ["## 2. Brief and assumptions", "", f"- **Category:** {b.category}", f"- **Audience:** {b.audience}",
          f"- **Objective:** {b.objective}", f"- **Markets:** {', '.join(b.markets)}"]
    if b.constraints:
        L.append(f"- **Constraints:** {b.constraints}")
    L.append("")
    for c in b.concepts:
        L.append(f"- **{c.name}:** {c.description}")
    L += ["", "## 3. Qloo signal map and resolved inputs", ""]
    if study.plan:
        L.append(f"Decision question: {study.plan.decision_question}\n")
        for s in study.plan.concept_seeds:
            ents = ", ".join(c.name for c in s.entity_candidates if c.selected) or "none"
            tags = ", ".join(c.name for c in s.tag_candidates if c.selected) or "none"
            L += [f"- **{names.get(s.concept_id, s.concept_id)}** - hypothesis: {s.hypothesis}",
                  f"  - Entities: {ents}", f"  - Tags: {tags}"]
    L += ["", "## 4. Side-by-side comparison", "",
          "| Concept | Coverage | Successful queries | Domains | Distinctive tags | Shared tags |", "|---|---|---|---|---|---|"]
    for p in study.profiles:
        L.append(f"| {names.get(p.concept_id)} | {p.coverage_label} | {p.calls_ok} ok / {p.calls_failed} failed / {p.calls_empty} empty | "
                 f"{', '.join(p.domains)} | {', '.join(p.distinctive_tags) or '-'} | {', '.join(p.shared_tags) or '-'} |")
    L += ["", "_Coverage and tags are CFST-derived summaries of returned evidence, not Qloo scores._", "",
          "## 5. Stress-test findings", ""]
    for a in study.assessments:
        L += [f"### {names.get(a.concept_id)} (confidence: {a.confidence})", "", f"_{a.confidence_rationale}_", ""]
        for title, sec in (("Aligned", a.aligned), ("Potential mismatch", a.mismatches), ("Distinctive territory", a.distinctive)):
            if sec:
                L.append(f"**{title}**")
                for f in sec:
                    refs = f" [{', '.join(f.evidence_ids)}]" if f.evidence_ids else ""
                    flag = f" _({f.flag})_" if f.flag else ""
                    L.append(f"- ({f.kind}) {f.statement}{refs}{flag}")
                L.append("")
        if a.localisation_question:
            L += [f"**Localisation question:** {a.localisation_question}", ""]
        if a.evidence_gaps:
            L += ["**Evidence gaps:**"] + [f"- {g}" for g in a.evidence_gaps] + [""]
        if a.alternative_direction:
            L += [f"**Alternative direction to test:** {a.alternative_direction}", ""]
    L += ["## 6. Recommended experiments", ""]
    for e in study.experiments:
        L += [f"### {e.priority}. {e.title}", f"- **Hypothesis:** {e.hypothesis}", f"- **Audience:** {e.audience}",
              f"- **Variable:** {e.variable}", f"- **Method:** {e.method}",
              f"- **Primary metric / guardrail:** {e.primary_metric} / {e.guardrail}",
              f"- **Decision informed:** {e.decision_informed}",
              f"- **Would change the recommendation if:** {e.result_that_changes_recommendation}",
              f"- **Effort:** {e.effort}", ""]
    L += ["## 7. Decision gates and unresolved questions", ""] + [f"- {q}" for q in study.open_questions] + [""]
    L += ["## 8. Appendix: evidence ledger", "", f"Limitations: {CAVEAT}", ""]
    for e in study.evidence:
        L += [f"### {e.id} - {names.get(e.concept_id)}{' - ' + e.market if e.market else ''}",
              f"- Purpose: {e.purpose}", f"- Output type: `{e.output_type}` | Mode: {e.mode} | Status: {e.status} | Retrieved: {e.retrieved_at}",
              f"- Input entities: {', '.join(x['name'] for x in e.input_entities) or '-'}",
              f"- Input tags: {', '.join(x['name'] for x in e.input_tags) or '-'}"]
        if e.location_context:
            L.append(f"- Location context: {e.location_context}")
        if e.error:
            L.append(f"- Error: {e.error}")
        if e.items:
            L.append("- Returned: " + "; ".join(i.name for i in e.items))
        L.append("")
    L += ["## 9. Methodology and skills", "",
          "Plan, stress test, audit, experiment planning and prose editing were run through the following installed skills:", ""]
    for s in study.skills_used:
        L.append(f"- `{s.skill}` ({s.stage}): {s.purpose}")
    L += ["", f"Qloo calls used: {study.qloo_calls_used}."]
    return "\n".join(L)

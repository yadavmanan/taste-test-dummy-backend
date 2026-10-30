from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..application.orchestrator import WorkflowError
from ..domain.models import Study
from ..skills import STAGE_SKILLS
from .dependencies import Container, get_container
from .schemas import CreateStudyRequest, SkillRunRequest, UpdateInputsRequest

router = APIRouter(prefix="/api")

DEMO_BRIEF = {
    "product_name": "Fizzora (fictional)",
    "category": "Sparkling functional beverage",
    "description": "A fictional low-sugar sparkling drink with botanical flavours, sold in cans, targeting urban young adults.",
    "audience": "Urban adults aged 22-35 who are active in food, music and design scenes",
    "objective": "Choose which positioning territory to validate first for launch in two markets",
    "decision": "Which concept should we take into concept testing, and does it travel between markets?",
    "markets": ["Mumbai", "Berlin"],
    "concepts": [
        {"id": "c1", "name": "Everyday Reset", "description": "An accessible, routine-led drink positioned around a small daily pause."},
        {"id": "c2", "name": "Creative Ritual", "description": "A design-forward drink connected to creative spaces, music and personal expression."},
        {"id": "c3", "name": "Natural Social Energy", "description": "A social, food-adjacent, outdoors-oriented concept built around gathering."},
    ],
    "constraints": "Premium-accessible price tier; cafe and specialty retail channels first",
    "reference_points": ["Blue Bottle Coffee"],
}


def _study(c: Container, study_id: str) -> Study:
    s = c.repo.get(study_id)
    if not s:
        raise HTTPException(404, "Study not found")
    return s


@router.get("/health")
async def health(c: Container = Depends(get_container)):
    return {
        "status": "ok",
        "qloo_live_available": c.qloo_live is not None,
        "llm_configured": c.llm_ready,
        "model": c.settings.openai_model,
        "skills_loaded": len(c.skills.registry.all()),
        "skills_dir": str(c.skills.registry.skills_dir),
        "qloo_call_budget": c.settings.qloo_call_budget,
    }


@router.get("/templates/demo")
async def demo_template():
    return DEMO_BRIEF


@router.get("/studies")
async def list_studies(c: Container = Depends(get_container)):
    return [
        {"id": s.id, "status": s.status, "mode": s.mode, "product_name": s.brief.product_name,
         "markets": s.brief.markets, "concepts": [x.name for x in s.brief.concepts], "created_at": s.created_at}
        for s in c.repo.list()
    ]


@router.post("/studies", status_code=201)
async def create_study(req: CreateStudyRequest, c: Container = Depends(get_container)):
    try:
        return c.orchestrator.create(req.brief, req.mode)
    except WorkflowError as exc:
        raise HTTPException(400, str(exc))


@router.get("/studies/{study_id}")
async def get_study(study_id: str, c: Container = Depends(get_container)):
    return _study(c, study_id)


@router.post("/studies/{study_id}/plan")
async def plan(study_id: str, c: Container = Depends(get_container)):
    try:
        return c.orchestrator.start_planning(study_id)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc))


@router.put("/studies/{study_id}/inputs")
async def update_inputs(study_id: str, req: UpdateInputsRequest, c: Container = Depends(get_container)):
    try:
        return c.orchestrator.update_inputs(study_id, req.concept_seeds)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise HTTPException(422, f"Invalid inputs: {exc}")


@router.post("/studies/{study_id}/run")
async def run(study_id: str, c: Container = Depends(get_container)):
    try:
        return c.orchestrator.start_run(study_id)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc))


@router.get("/studies/{study_id}/report.md", response_class=PlainTextResponse)
async def report(study_id: str, c: Container = Depends(get_container)):
    s = _study(c, study_id)
    if not s.report_markdown:
        raise HTTPException(409, "Report not available yet")
    return PlainTextResponse(s.report_markdown, headers={"Content-Disposition": f'attachment; filename="{s.id}-report.md"'})


@router.get("/qloo/entities")
async def search_entities(query: str = Query(min_length=2, max_length=80), mode: str = "live",
                          c: Container = Depends(get_container)):
    qloo = c.qloo_live if mode == "live" else c.qloo_fixture
    if not qloo:
        raise HTTPException(400, "Live Qloo is not configured")
    try:
        return await qloo.search_entities(query, take=6)
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/qloo/tags")
async def search_tags(query: str = Query(min_length=2, max_length=80), mode: str = "live",
                      c: Container = Depends(get_container)):
    qloo = c.qloo_live if mode == "live" else c.qloo_fixture
    if not qloo:
        raise HTTPException(400, "Live Qloo is not configured")
    try:
        return await qloo.search_tags(query, take=8)
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/skills")
async def list_skills(c: Container = Depends(get_container)):
    return {
        "skills": c.skills.catalog(),
        "stage_bindings": {k: {"skill": v[0], "purpose": v[1]} for k, v in STAGE_SKILLS.items()},
    }


@router.get("/skills/{name}")
async def skill_detail(name: str, c: Container = Depends(get_container)):
    d = c.skills.detail(name)
    if not d:
        raise HTTPException(404, "Skill not found")
    return d


@router.post("/skills/{name}/run")
async def run_skill(name: str, req: SkillRunRequest, c: Container = Depends(get_container)):
    if not c.skills.registry.get(name):
        raise HTTPException(404, "Skill not found")
    try:
        result = await c.skills.apply(name, req.task, req.input, json_output=req.json_output)
    except Exception as exc:
        raise HTTPException(502, f"Skill execution failed: {exc}")
    return {"skill": name, "result": result}

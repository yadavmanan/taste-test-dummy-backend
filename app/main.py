from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.dependencies import Container
from .api.routes import router
from .application.orchestrator import StudyOrchestrator
from .config import get_settings
from .infrastructure.json_repository import JsonFileStudyRepository
from .integrations.fixture_qloo import FixtureQlooAdapter
from .integrations.openai_client import OpenAIChatAdapter
from .integrations.qloo_client import QlooHttpAdapter
from .skills import SkillExecutor, SkillRegistry


def build_container() -> Container:
    s = get_settings()
    qloo_live = QlooHttpAdapter(s.qloo_base_url, s.qloo_api_key, s.qloo_concurrency) if s.qloo_configured else None
    qloo_fixture = FixtureQlooAdapter()
    llm = OpenAIChatAdapter(s.openai_base_url, s.openai_api_key, s.openai_model, s.openai_fallback_models)
    skills = SkillExecutor(SkillRegistry(s.skills_dir), llm)
    repo = JsonFileStudyRepository(s.data_dir)
    orchestrator = StudyOrchestrator(repo, qloo_live, qloo_fixture, skills, llm, s)
    return Container(settings=s, repo=repo, orchestrator=orchestrator, skills=skills,
                     qloo_live=qloo_live, qloo_fixture=qloo_fixture, llm_ready=s.llm_configured)


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = build_container()
    container.orchestrator.recover_interrupted()
    app.state.container = container
    yield
    if container.qloo_live:
        await container.qloo_live.aclose()  # type: ignore[attr-defined]


app = FastAPI(title="Cultural Fit Stress Tester", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=get_settings().allowed_origins, allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router)

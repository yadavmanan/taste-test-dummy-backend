from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from ..application.orchestrator import StudyOrchestrator
from ..config import Settings
from ..domain.ports import QlooPort, StudyRepository
from ..skills import SkillExecutor


@dataclass
class Container:
    settings: Settings
    repo: StudyRepository
    orchestrator: StudyOrchestrator
    skills: SkillExecutor
    qloo_live: Optional[QlooPort]
    qloo_fixture: QlooPort
    llm_ready: bool


def get_container(request: Request) -> Container:
    return request.app.state.container

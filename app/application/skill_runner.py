from __future__ import annotations

from typing import Any, Callable

from ..domain.models import Study
from ..domain.ports import SkillPort
from ..skills.bindings import STAGE_SKILLS

Emit = Callable[..., None]


class SkillRunner:
    """Applies the skill bound to a workflow stage and records the use on the study."""

    def __init__(self, skills: SkillPort):
        self.skills = skills

    async def run(self, study: Study, stage: str, task: str, payload: Any, json_output: bool = True,
                  skill: str | None = None, purpose: str | None = None) -> Any:
        from ..domain.models import SkillUse

        bound_skill, bound_purpose = STAGE_SKILLS[stage]
        skill = skill or bound_skill
        study.skills_used.append(SkillUse(stage=stage, skill=skill, purpose=purpose or bound_purpose))
        return await self.skills.apply(skill, task, payload, json_output=json_output)

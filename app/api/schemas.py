from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, Field

from ..domain.models import LaunchBrief


class CreateStudyRequest(BaseModel):
    brief: LaunchBrief
    mode: str = Field(default="live", pattern="^(live|fixture)$")


class UpdateInputsRequest(BaseModel):
    concept_seeds: list[dict[str, Any]]


class SkillRunRequest(BaseModel):
    task: str = Field(min_length=3, max_length=2000)
    input: Union[str, dict, list] = ""
    json_output: bool = False
    mode: Optional[str] = None

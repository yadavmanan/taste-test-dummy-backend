"""Ports: interfaces the application layer depends on. Adapters implement them."""
from __future__ import annotations

from typing import Any, Optional, Protocol

from .models import Study


class QlooPort(Protocol):
    mode: str

    async def search_entities(self, query: str, types: Optional[str] = None, take: int = 5) -> list[dict]: ...

    async def search_tags(self, query: str, take: int = 5) -> list[dict]: ...

    async def insights(self, params: dict[str, Any]) -> list[dict]: ...


class LLMPort(Protocol):
    async def complete_json(self, system: str, user: str, temperature: float = 0.3) -> dict: ...

    async def complete_text(self, system: str, user: str, temperature: float = 0.3) -> str: ...


class StudyRepository(Protocol):
    def save(self, study: Study) -> None: ...

    def get(self, study_id: str) -> Optional[Study]: ...

    def list(self) -> list[Study]: ...


class SkillPort(Protocol):
    def catalog(self) -> list[dict]: ...

    def detail(self, name: str) -> Optional[dict]: ...

    async def apply(self, skill: str, task: str, payload: Any, json_output: bool = True) -> Any: ...

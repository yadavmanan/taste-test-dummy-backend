from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Skill:
    name: str
    folder: str
    description: str
    body: str
    path: str
    metadata: dict = field(default_factory=dict)
    resources: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "name": self.name,
            "folder": self.folder,
            "description": self.description,
            "resources": len(self.resources),
            "chars": len(self.body),
        }


_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)


def _parse(text: str) -> tuple[dict, str]:
    m = _FM.match(text.lstrip("\ufeff"))
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except yaml.YAMLError:
        meta = {}
        for key in ("name", "description"):
            mm = re.search(rf"^{key}:\s*(.+)$", m.group(1), re.M)
            if mm:
                meta[key] = mm.group(1).strip().strip('"')
    return meta, m.group(2)


class SkillRegistry:
    """Discovers <skills_dir>/<folder>/SKILL.md files and exposes them by folder name or frontmatter name."""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        if not self.skills_dir.is_dir():
            return
        for folder in sorted(p for p in self.skills_dir.iterdir() if p.is_dir()):
            f = folder / "SKILL.md"
            if not f.is_file():
                continue
            meta, body = _parse(f.read_text(encoding="utf-8", errors="replace"))
            resources = [
                str(p.relative_to(folder)).replace("\\", "/")
                for p in folder.rglob("*.md")
                if p.name != "SKILL.md"
            ][:50]
            desc = " ".join(str(meta.get("description", "")).split())
            self._skills[folder.name] = Skill(
                name=str(meta.get("name") or folder.name),
                folder=folder.name,
                description=desc,
                body=body.strip(),
                path=str(f),
                metadata=meta.get("metadata") or {},
                resources=resources,
            )

    def get(self, key: str) -> Optional[Skill]:
        if key in self._skills:
            return self._skills[key]
        for s in self._skills.values():
            if s.name == key:
                return s
        return None

    def all(self) -> list[Skill]:
        return list(self._skills.values())

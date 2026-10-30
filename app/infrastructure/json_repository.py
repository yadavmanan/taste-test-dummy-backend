from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from ..domain.models import Study, now_iso


class JsonFileStudyRepository:
    """File-backed repository; one JSON document per study."""

    def __init__(self, data_dir: Path):
        self.dir = data_dir / "studies"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: dict[str, Study] = {}
        for p in self.dir.glob("*.json"):
            try:
                s = Study.model_validate(json.loads(p.read_text(encoding="utf-8")))
                self._cache[s.id] = s
            except Exception:
                continue

    def _path(self, study_id: str) -> Path:
        safe = "".join(c for c in study_id if c.isalnum() or c in "_-")
        return self.dir / f"{safe}.json"

    def save(self, study: Study) -> None:
        study.updated_at = now_iso()
        self._cache[study.id] = study
        with self._lock:
            tmp = self._path(study.id).with_suffix(".tmp")
            tmp.write_text(study.model_dump_json(indent=1), encoding="utf-8")
            tmp.replace(self._path(study.id))

    def get(self, study_id: str) -> Optional[Study]:
        return self._cache.get(study_id)

    def list(self) -> list[Study]:
        return sorted(self._cache.values(), key=lambda s: s.created_at, reverse=True)

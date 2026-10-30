from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx


class QlooError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class QlooHttpAdapter:
    """Live Qloo adapter. Key stays server-side; only documented endpoints are used."""

    mode = "live"

    def __init__(self, base_url: str, api_key: str, concurrency: int = 4, timeout: float = 45.0):
        self._client = httpx.AsyncClient(
            base_url=base_url, headers={"X-Api-Key": api_key}, timeout=timeout
        )
        self._sem = asyncio.Semaphore(concurrency)
        self._cache: dict[tuple, Any] = {}

    async def _get(self, path: str, params: dict[str, Any]) -> dict:
        key = (path, tuple(sorted((k, str(v)) for k, v in params.items())))
        if key in self._cache:
            return self._cache[key]
        last: Optional[Exception] = None
        for attempt in range(3):
            try:
                async with self._sem:
                    resp = await self._client.get(path, params=params)
                if resp.status_code in (429, 502, 503, 504):
                    last = QlooError(f"Qloo temporary error {resp.status_code}", resp.status_code)
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                if resp.status_code >= 400:
                    detail = resp.text[:300]
                    raise QlooError(f"Qloo {resp.status_code} on {path}: {detail}", resp.status_code)
                data = resp.json()
                self._cache[key] = data
                return data
            except httpx.HTTPError as exc:
                last = QlooError(f"Qloo network error: {exc.__class__.__name__}")
                await asyncio.sleep(1.0 * (attempt + 1))
        raise last or QlooError("Qloo request failed")

    async def search_entities(self, query: str, types: Optional[str] = None, take: int = 5) -> list[dict]:
        params: dict[str, Any] = {"query": query, "take": take}
        if types:
            params["types"] = types
        data = await self._get("/search", params)
        out = []
        for r in data.get("results", []):
            props = r.get("properties") or {}
            out.append(
                {
                    "entity_id": r.get("entity_id"),
                    "name": r.get("name"),
                    "type": (r.get("types") or [""])[0],
                    "description": (props.get("short_description") or props.get("description") or "")[:240],
                    "popularity": r.get("popularity"),
                    "disambiguation": r.get("disambiguation"),
                }
            )
        return out

    async def search_tags(self, query: str, take: int = 5) -> list[dict]:
        data = await self._get("/v2/tags", {"filter.query": query, "take": take, "feature.typo_tolerance": "true"})
        out = []
        for t in (data.get("results") or {}).get("tags", []):
            out.append(
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "type": t.get("type", ""),
                    "parents": [p.get("type") for p in t.get("parents", [])],
                    "popularity": t.get("popularity"),
                }
            )
        return out

    async def insights(self, params: dict[str, Any]) -> list[dict]:
        data = await self._get("/v2/insights", {**params, "feature.explainability": "true"})
        out = []
        for e in (data.get("results") or {}).get("entities", []):
            props = e.get("properties") or {}
            q = e.get("query") or {}
            expl = (q.get("explainability") or {}).get("signal.interests.entities", [])
            out.append(
                {
                    "entity_id": e.get("entity_id"),
                    "name": e.get("name"),
                    "type": e.get("subtype") or e.get("type") or "",
                    "affinity": q.get("affinity"),
                    "popularity": e.get("popularity"),
                    "tags": [t.get("name") for t in e.get("tags", []) if t.get("name")][:8],
                    "description": (props.get("short_description") or props.get("description") or "")[:240],
                    "explained_by": [x.get("entity_id") for x in expl if x.get("entity_id")],
                }
            )
        return out

    async def aclose(self) -> None:
        await self._client.aclose()

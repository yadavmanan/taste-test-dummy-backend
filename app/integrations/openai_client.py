from __future__ import annotations

import json
import re
from typing import Optional

import httpx


class LLMError(Exception):
    pass


def extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


class OpenAIChatAdapter:
    """OpenAI-compatible chat completions client (base URL and model come from settings)."""

    def __init__(self, base_url: str, api_key: str, model: str, fallbacks: tuple = (), timeout: float = 180.0):
        self._client = httpx.AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
        )
        self._models = [model, *[m for m in fallbacks if m != model]]
        self._active = 0

    async def _chat(self, system: str, user: str, temperature: float, json_mode: bool) -> str:
        last: Optional[str] = None
        while self._active < len(self._models):
            model = self._models[self._active]
            body = {
                "model": model,
                "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            try:
                resp = await self._client.post("/chat/completions", json=body)
            except httpx.HTTPError as exc:
                last = f"network error {exc.__class__.__name__}"
                raise LLMError(last)
            if resp.status_code in (401, 403, 400, 404):
                last = f"{model}: {resp.text[:200]}"
                self._active += 1  # model not usable for this account; try the next one
                continue
            if resp.status_code >= 400:
                raise LLMError(f"LLM {resp.status_code}: {resp.text[:200]}")
            content = (resp.json()["choices"][0]["message"].get("content") or "").strip()
            if content:
                return content
            last = f"{model}: empty response"
            self._active += 1
        raise LLMError(last or "No usable LLM model")

    async def complete_json(self, system: str, user: str, temperature: float = 0.3) -> dict:
        system = system + "\n\nRespond with a single valid JSON object only. No prose, no markdown fences."
        for attempt in range(2):
            raw = await self._chat(system, user, temperature, json_mode=True)
            try:
                return extract_json(raw)
            except json.JSONDecodeError:
                user = user + "\n\nYour previous reply was not valid JSON. Return only valid JSON."
        raise LLMError("Model did not return valid JSON")

    async def complete_text(self, system: str, user: str, temperature: float = 0.3) -> str:
        return await self._chat(system, user, temperature, json_mode=False)

    async def aclose(self) -> None:
        await self._client.aclose()

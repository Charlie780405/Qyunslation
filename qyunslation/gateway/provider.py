# SPDX-License-Identifier: MPL-2.0
"""PLAN-034f：TranslatorProvider（Qwen/Ollama chat，不改 Agent 主循环）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from qyunslation.gateway.config import resolve_profile


class TranslatorProvider(Protocol):
    def translate(self, source: str, *, system: str | None = None) -> str: ...
    def review(self, source: str, target: str, *, findings: list[str] | None = None) -> str: ...
    def repair(self, source: str, target: str, *, findings: list[str] | None = None) -> str: ...


@dataclass
class QwenOllamaProvider:
    """OpenAI-compatible chat against Ollama / gateway endpoint."""

    model_id: str
    base_url: str
    api_key: str = "ollama"
    timeout: float = 120.0

    def _chat(self, messages: list[dict[str, str]]) -> str:
        root = self.base_url.rstrip("/")
        if root.endswith("/v1"):
            url = f"{root}/chat/completions"
        else:
            url = f"{root}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": 0.1,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        return str(msg.get("content") or "").strip()

    def translate(self, source: str, *, system: str | None = None) -> str:
        sys = system or "Translate the following medical text accurately. Keep numbers, units, and citations unchanged."
        return self._chat(
            [
                {"role": "system", "content": sys},
                {"role": "user", "content": source},
            ]
        )

    def review(self, source: str, target: str, *, findings: list[str] | None = None) -> str:
        notes = "; ".join(findings or []) or "none"
        prompt = (
            f"Source:\n{source}\n\nTranslation:\n{target}\n\n"
            f"Known QA findings: {notes}\n"
            "Reply with a short review: PASS or issues."
        )
        return self._chat(
            [
                {"role": "system", "content": "You are a medical translation reviewer."},
                {"role": "user", "content": prompt},
            ]
        )

    def repair(self, source: str, target: str, *, findings: list[str] | None = None) -> str:
        notes = "; ".join(findings or []) or "none"
        prompt = (
            f"Source:\n{source}\n\nCurrent translation:\n{target}\n\n"
            f"Fix these issues: {notes}\n"
            "Return ONLY the corrected translation."
        )
        return self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Repair the translation. Preserve numbers, doses, units, "
                        "percentages, dates, and citation markers."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )


def get_provider(*, profile: str | None = None, api_key: str | None = None) -> QwenOllamaProvider:
    resolved = resolve_profile(profile)
    endpoint = resolved["endpoint"] or (os.environ.get("QYUNSLATION_BASE_URL") or "").strip()
    if not endpoint:
        raise ValueError("gateway endpoint missing: set QYUNSLATION_BASE_URL or DOCUTRANSLATE_BASE_URL")
    key = (
        api_key
        or os.environ.get("QYUNSLATION_API_KEY")
        or os.environ.get("DOCUTRANSLATE_API_KEY")
        or "ollama"
    )
    return QwenOllamaProvider(
        model_id=resolved["model_id"],
        base_url=endpoint,
        api_key=key,
    )


def ping_provider(*, profile: str | None = None) -> dict[str, Any]:
    """轻量可达性探测；失败由 verify 记 BLOCKED。"""
    try:
        provider = get_provider(profile=profile)
        root = provider.base_url.rstrip("/")
        # 优先 /api/tags（Ollama），否则试 /v1/models
        with httpx.Client(timeout=5.0) as client:
            for path in ("/api/tags", "/v1/models"):
                base = root[: -len("/v1")] if root.endswith("/v1") else root
                url = f"{base}{path}" if path.startswith("/api") else f"{root if root.endswith('/v1') else root + '/v1'}/models"
                if path == "/api/tags":
                    url = f"{base}/api/tags"
                try:
                    r = client.get(url)
                    if r.status_code < 500:
                        return {
                            "ok": True,
                            "model_id": provider.model_id,
                            "status_code": r.status_code,
                            "url": url,
                        }
                except httpx.HTTPError:
                    continue
        return {"ok": False, "model_id": provider.model_id, "error": "unreachable"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

# SPDX-License-Identifier: MPL-2.0
"""PLAN-055：泰州 Ollama bge-m3 embedding HTTP 客户端。

契约与 Hermes mcp/embed-mcp 相同（禁止分叉）：
  POST {OLLAMA_EMBED_URL}/api/embed
  {"model": "...", "input": ["..."]} → {"embeddings": [[float, ...], ...]}
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Sequence

DEFAULT_URL = "http://100.67.66.123:11434"
DEFAULT_MODEL = "bge-m3"
DEFAULT_DIM = 1024
DEFAULT_TIMEOUT = 30.0
MAX_BATCH = 32
MAX_CHARS = 8000


class EmbedError(RuntimeError):
    """embedding 调用失败（维数/HTTP/超时）。"""


def _url() -> str:
    return (os.environ.get("OLLAMA_EMBED_URL") or DEFAULT_URL).rstrip("/")


def _model() -> str:
    return (os.environ.get("OLLAMA_EMBED_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _dim() -> int:
    try:
        return int(os.environ.get("OLLAMA_EMBED_DIM") or DEFAULT_DIM)
    except ValueError:
        return DEFAULT_DIM


def _timeout() -> float:
    try:
        return float(os.environ.get("OLLAMA_EMBED_TIMEOUT") or DEFAULT_TIMEOUT)
    except ValueError:
        return DEFAULT_TIMEOUT


def embed_health() -> dict[str, Any]:
    """探活：GET /api/tags，检查模型是否在列表中。"""
    base = _url()
    model = _model()
    try:
        req = urllib.request.Request(f"{base}/api/tags")
        with urllib.request.urlopen(req, timeout=_timeout()) as resp:
            data = json.loads(resp.read().decode())
        names = [
            str(m.get("name") or m.get("model") or "")
            for m in (data.get("models") or [])
        ]
        has = any(model in n or n.startswith(model) for n in names if n)
        return {
            "ok": True,
            "url": base,
            "model": model,
            "has_bge_m3": has,
            "model_match": has,
            "live": has,
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": base,
            "model": model,
            "model_match": False,
            "live": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """批嵌入；空列表返回 []；失败抛 EmbedError。"""
    if not texts:
        return []
    if len(texts) > MAX_BATCH:
        raise EmbedError(f"batch size {len(texts)} exceeds {MAX_BATCH}")
    cleaned: list[str] = []
    for i, t in enumerate(texts):
        if not isinstance(t, str):
            raise EmbedError(f"texts[{i}] must be str")
        if len(t) > MAX_CHARS:
            raise EmbedError(f"texts[{i}] exceeds {MAX_CHARS} chars")
        cleaned.append(t)
    model = _model()
    dim = _dim()
    payload = json.dumps({"model": model, "input": cleaned}).encode()
    req = urllib.request.Request(
        f"{_url()}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_timeout()) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise EmbedError(f"HTTP {exc.code}: {exc.reason}") from exc
    except Exception as exc:
        raise EmbedError(f"{type(exc).__name__}: {exc}") from exc
    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(cleaned):
        raise EmbedError("embeddings length mismatch")
    out: list[list[float]] = []
    for i, vec in enumerate(embeddings):
        if not isinstance(vec, list) or len(vec) != dim:
            got = len(vec) if isinstance(vec, list) else type(vec).__name__
            raise EmbedError(f"embeddings[{i}] dim {got} != {dim}")
        out.append([float(x) for x in vec])
    return out

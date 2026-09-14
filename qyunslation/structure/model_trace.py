# SPDX-License-Identifier: MPL-2.0
"""PLAN-033g：记录最终解析后的模型与去凭据 endpoint。"""
from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SECRET_MARKERS = ("api_key", "authorization", "sk-", "token=", "password")
EXPECTED_TRANSLATION_MODEL = "qwen3.6:35b-a3b"
EXPECTED_EMBEDDING_MODEL = "bge-m3"
_CURRENT_TRACE: ContextVar[dict[str, Any] | None] = ContextVar(
    "qyunslation_model_trace", default=None
)


def strip_endpoint(endpoint: str) -> str:
    parts = urlsplit((endpoint or "").strip())
    host = parts.hostname or ""
    if not host:
        return parts.path.rstrip("?")
    netloc = host if parts.port is None else f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def build_model_trace(
    *,
    model_id: str,
    endpoint: str,
    extras: dict | None = None,
) -> dict[str, Any]:
    if extras:
        blob = str(extras).lower()
        if any(marker in blob for marker in _SECRET_MARKERS):
            raise ValueError("MODEL_TRACE_SECRET: credentials must not be recorded")
    trace = {
        "model_id": str(model_id).strip(),
        "endpoint": strip_endpoint(endpoint),
    }
    dumped = str(trace).lower()
    if any(marker in dumped for marker in _SECRET_MARKERS):
        raise ValueError("MODEL_TRACE_SECRET: credentials must not be recorded")
    # Keep the historical two-field trace stable when no extra provenance is
    # supplied.  New callers can attach non-secret runtime evidence without
    # creating a second manifest format.
    if extras:
        for key, value in extras.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                continue
            if "endpoint" in normalized_key.lower():
                value = strip_endpoint(str(value))
            trace[normalized_key] = value
    return trace


def resolve_model_trace(
    *,
    model_id: str | None,
    endpoint: str | None,
    default_model_id: str | None = None,
    default_endpoint: str | None = None,
) -> dict[str, Any]:
    resolved_model = (model_id or "").strip() or (default_model_id or "").strip()
    resolved_endpoint = (endpoint or "").strip() or (default_endpoint or "").strip()
    if not resolved_model or not resolved_endpoint:
        raise ValueError("MODEL_TRACE_INCOMPLETE: model_id and endpoint are required")
    return build_model_trace(model_id=resolved_model, endpoint=resolved_endpoint)


def attach_model_trace(manifest, **kwargs) -> None:
    manifest.extensions["model_trace"] = resolve_model_trace(**kwargs)


def bind_task_model_trace(
    *,
    model_id: str | None,
    endpoint: str | None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trace = resolve_model_trace(model_id=model_id, endpoint=endpoint)
    if extras:
        trace = build_model_trace(
            model_id=trace["model_id"], endpoint=trace["endpoint"], extras=extras
        )
    _CURRENT_TRACE.set(trace)
    return trace


def current_model_trace() -> dict[str, Any] | None:
    return _CURRENT_TRACE.get()


def trace_from_env() -> dict[str, str] | None:
    model = (
        os.environ.get("QYUNSLATION_MODEL_ID")
        or os.environ.get("DOCUTRANSLATE_MODEL_ID")
        or ""
    ).strip()
    endpoint = (
        os.environ.get("QYUNSLATION_BASE_URL")
        or os.environ.get("DOCUTRANSLATE_BASE_URL")
        or ""
    ).strip()
    if not model or not endpoint:
        return None
    return resolve_model_trace(model_id=model, endpoint=endpoint)


def apply_current_model_trace(manifest) -> None:
    trace = current_model_trace()
    if not trace:
        try:
            trace = trace_from_env()
        except ValueError:
            trace = None
        if trace:
            _CURRENT_TRACE.set(trace)
    if trace:
        manifest.extensions["model_trace"] = dict(trace)

# SPDX-License-Identifier: MPL-2.0
"""PLAN-033g：记录最终解析后的模型与去凭据 endpoint。"""
from __future__ import annotations

from contextvars import ContextVar
from urllib.parse import urlsplit, urlunsplit

_SECRET_MARKERS = ("api_key", "authorization", "sk-", "token=", "password")
_CURRENT_TRACE: ContextVar[dict[str, str] | None] = ContextVar(
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
) -> dict[str, str]:
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
    return trace


def resolve_model_trace(
    *,
    model_id: str | None,
    endpoint: str | None,
    default_model_id: str | None = None,
    default_endpoint: str | None = None,
) -> dict[str, str]:
    resolved_model = (model_id or "").strip() or (default_model_id or "").strip()
    resolved_endpoint = (endpoint or "").strip() or (default_endpoint or "").strip()
    if not resolved_model or not resolved_endpoint:
        raise ValueError("MODEL_TRACE_INCOMPLETE: model_id and endpoint are required")
    return build_model_trace(model_id=resolved_model, endpoint=resolved_endpoint)


def attach_model_trace(manifest, **kwargs) -> None:
    manifest.extensions["model_trace"] = resolve_model_trace(**kwargs)


def bind_task_model_trace(*, model_id: str | None, endpoint: str | None) -> dict[str, str]:
    trace = resolve_model_trace(model_id=model_id, endpoint=endpoint)
    _CURRENT_TRACE.set(trace)
    return trace


def current_model_trace() -> dict[str, str] | None:
    return _CURRENT_TRACE.get()


def apply_current_model_trace(manifest) -> None:
    trace = current_model_trace()
    if trace:
        manifest.extensions["model_trace"] = dict(trace)

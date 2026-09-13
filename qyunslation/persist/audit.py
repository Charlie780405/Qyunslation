# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c：审计写入（剥离密钥类字段）。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from qyunslation.persist.models import AuditEvent

_SECRET_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "api-key",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "bearer",
    }
)


def sanitize_extra(extra: dict[str, Any] | None) -> dict[str, Any] | None:
    if not extra:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in extra.items():
        if str(key).strip().lower() in _SECRET_KEYS:
            continue
        cleaned[key] = value
    return cleaned or None


def record_audit(
    session: Session,
    *,
    actor_sub: str,
    action: str,
    source_sha256: str | None = None,
    extra: dict[str, Any] | None = None,
    note: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_sub=actor_sub,
        action=action,
        source_sha256=source_sha256,
        extra=sanitize_extra(extra),
        note=note,
    )
    session.add(event)
    session.flush()
    return event

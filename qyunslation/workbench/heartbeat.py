# SPDX-License-Identifier: MPL-2.0
"""PLAN-072b：TranslationRun 心跳与 stale 判定。"""
from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from qyunslation.persist.models import TranslationRunRecord

NON_TERMINAL_RUN_STATUSES = frozenset(
    {"queued", "scanning", "translating", "rendering", "interrupted"}
)


def heartbeat_stale_seconds() -> int:
    raw = (os.environ.get("QYUNSLATION_RUN_HEARTBEAT_STALE_SEC") or "120").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 120


def lease_owner_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def touch_run_heartbeat(session: Session, run: TranslationRunRecord) -> None:
    run.heartbeat_at = datetime.now(timezone.utc)
    run.lease_owner = lease_owner_id()
    run.updated_at = run.heartbeat_at
    session.flush()


def is_heartbeat_stale(run: TranslationRunRecord, *, now: datetime | None = None) -> bool:
    if run.heartbeat_at is None:
        return run.status in {"queued", "scanning", "translating", "rendering"}
    moment = now or datetime.now(timezone.utc)
    hb = run.heartbeat_at
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=timezone.utc)
    return (moment - hb) > timedelta(seconds=heartbeat_stale_seconds())


def mark_interrupted(session: Session, run: TranslationRunRecord, *, reason: str) -> None:
    run.status = "interrupted"
    run.degradation_reason = reason[:512]
    run.lease_owner = None
    run.updated_at = datetime.now(timezone.utc)
    session.flush()

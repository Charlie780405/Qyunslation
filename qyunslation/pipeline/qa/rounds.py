# SPDX-License-Identifier: MPL-2.0
"""PLAN-078a：QA 检查轮次的登记、抢占与后台派发。

A round is the unit of "one QA evaluation of a run's current output". Registering it is
cheap and safe to do from a read path; the evaluation itself runs elsewhere
(``submit_background`` in production, inline in tests). The database guarantees that a run
generation has at most one live round, so repeated polls, double clicks and several
browser tabs cannot start duplicate checks.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qyunslation.persist.models import QaCheckRound

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "running")


def _env_seconds(name: str, default: int) -> int:
    try:
        return max(5, int((os.environ.get(name) or "").strip() or default))
    except ValueError:
        return default


def pending_lease_seconds() -> int:
    """How long a registered round may wait for a worker before it is re-dispatched."""
    return _env_seconds("QYUNSLATION_QA_PENDING_LEASE_SEC", 120)


def running_lease_seconds() -> int:
    """How long a running round may go without finishing before another worker takes over."""
    return _env_seconds("QYUNSLATION_QA_LEASE_SEC", 600)


def qa_mode() -> str:
    """``background`` (default) or ``inline`` (deterministic, used by tests and scripts)."""
    return "inline" if (os.environ.get("QYUNSLATION_QA_MODE") or "").strip().casefold() == "inline" else "background"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def active_round(session: Session, run_id: str, generation: int) -> QaCheckRound | None:
    return session.scalar(
        select(QaCheckRound).where(
            QaCheckRound.run_id == run_id,
            QaCheckRound.generation == generation,
            QaCheckRound.status.in_(ACTIVE_STATUSES),
        )
    )


def latest_round(session: Session, run_id: str, generation: int) -> QaCheckRound | None:
    return session.scalar(
        select(QaCheckRound)
        .where(QaCheckRound.run_id == run_id, QaCheckRound.generation == generation)
        .order_by(QaCheckRound.round_no.desc())
        .limit(1)
    )


def ensure_round(
    session: Session, run_id: str, generation: int, *, trigger: str
) -> tuple[QaCheckRound | None, bool]:
    """Register a round unless a live one exists. Returns ``(round, created)``.

    A round whose lease has run out (worker died, process restarted before dispatch) is
    closed as failed and replaced, so a run can never be stuck "checking" forever.
    """
    now = _now()
    current = active_round(session, run_id, generation)
    if current is not None:
        if (_aware(current.lease_until) or now) > now:
            return current, False
        current.status = "failed"
        current.error_code = "lease_expired"
        current.finished_at = now
        session.flush()
    next_no = (
        session.scalar(
            select(func.max(QaCheckRound.round_no)).where(
                QaCheckRound.run_id == run_id, QaCheckRound.generation == generation
            )
        )
        or 0
    ) + 1
    row = QaCheckRound(
        run_id=run_id,
        generation=generation,
        round_no=next_no,
        trigger=trigger,
        status="pending",
        lease_until=now + timedelta(seconds=pending_lease_seconds()),
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        # Another request registered a round first; theirs is the one that will run.
        return active_round(session, run_id, generation), False
    return row, True


def claim_round(session: Session, round_id: str) -> bool:
    """Atomically move pending -> running. Only one worker can win."""
    now = _now()
    result = session.execute(
        update(QaCheckRound)
        .where(QaCheckRound.id == round_id, QaCheckRound.status == "pending")
        .values(
            status="running",
            started_at=now,
            lease_until=now + timedelta(seconds=running_lease_seconds()),
        )
    )
    session.flush()
    return result.rowcount == 1


def finish_round(session: Session, round_id: str, *, ok: bool, error_code: str | None = None) -> None:
    session.execute(
        update(QaCheckRound)
        .where(QaCheckRound.id == round_id)
        .values(status="succeeded" if ok else "failed", error_code=error_code, finished_at=_now())
    )
    session.flush()


_POOL: ThreadPoolExecutor | None = None


def submit_background(fn: Callable[..., Any], *args: Any) -> None:
    """Run ``fn`` on the QA worker pool; failures are logged, never raised to the caller."""
    global _POOL
    if _POOL is None:
        workers = max(1, int((os.environ.get("QYUNSLATION_QA_WORKERS") or "2").strip() or 2))
        _POOL = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="qa-round")

    def _log_failure(future: Any) -> None:
        error = future.exception()
        if error is not None:
            logger.error("QA round worker crashed", exc_info=error)

    _POOL.submit(fn, *args).add_done_callback(_log_failure)

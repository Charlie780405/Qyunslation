#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-063e：为历史 plan062 purge 拒绝补记 TermDecision，不改候选状态。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from qyunslation.persist.db import get_database_url, init_engine, reset_engine  # noqa: E402
from qyunslation.persist.models import DocumentTermCandidate, TermDecision  # noqa: E402

PREFIX = "plan062 purge:"
ACTOR = "plan062-purge"


def backfill_machine_decisions(session) -> int:
    existing = {
        row.candidate_id
        for row in session.scalars(
            select(TermDecision).where(TermDecision.actor_sub == ACTOR)
        ).all()
    }
    minted = 0
    stmt = select(DocumentTermCandidate).where(
        DocumentTermCandidate.status == "rejected",
        DocumentTermCandidate.decision_note.is_not(None),
    )
    for candidate in session.scalars(stmt).all():
        note = candidate.decision_note or ""
        if not note.startswith(PREFIX):
            continue
        if candidate.id in existing:
            continue
        session.add(
            TermDecision(
                candidate_id=candidate.id,
                action="reject",
                actor_sub=ACTOR,
                source_term=candidate.source_term,
                target_term=candidate.suggested_target or candidate.observed_target or "",
                concept_id=candidate.concept_id,
                scope="project",
                from_version=max(int(candidate.version or 1) - 1, 1),
                to_version=int(candidate.version or 1),
                note=note,
            )
        )
        existing.add(candidate.id)
        minted += 1
    if minted:
        session.flush()
    return minted


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill TermDecision for plan062 purge rejects")
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    url = args.database_url or get_database_url()
    if not url:
        print("FAIL: set QYUNSLATION_DATABASE_URL or --database-url", file=sys.stderr)
        return 1
    reset_engine()
    init_engine(url)
    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    session = SessionLocal()
    try:
        minted = backfill_machine_decisions(session)
        if args.apply:
            session.commit()
        mode = "apply" if args.apply else "dry-run"
        print(f"mode={mode} backfilled={minted}")
        if not args.apply:
            session.rollback()
    finally:
        session.close()
        reset_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

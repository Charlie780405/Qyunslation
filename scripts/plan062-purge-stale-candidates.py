#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-062a / PLAN-063e：按准入规则回扫 pending，机器裁决写入 TermDecision。"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from qyunslation.glossary.candidate_rules import should_exclude_from_termbase  # noqa: E402
from qyunslation.glossary.governance import normalize_source  # noqa: E402
from qyunslation.persist.audit import record_audit  # noqa: E402
from qyunslation.persist.candidate_repo import decide_candidate, record_machine_decision  # noqa: E402
from qyunslation.persist.db import get_database_url, init_engine, reset_engine  # noqa: E402
from qyunslation.persist.models import Concept, ConceptTerm, DocumentTermCandidate  # noqa: E402

PURGE_STATUSES = frozenset({"pending", "pending_admin"})


def find_curated_concept(session: Session, source_term: str) -> Concept | None:
    source_norm = normalize_source(source_term)
    return session.scalar(
        select(Concept)
        .join(ConceptTerm)
        .where(Concept.status == "curated")
        .where(ConceptTerm.normalized_text == source_norm)
        .order_by(Concept.layer, Concept.id)
    )


def classify_purge_action(
    session: Session, candidate: DocumentTermCandidate
) -> tuple[str, str, str | None]:
    """返回 (reject|apply|keep, note, concept_id)。"""
    excluded, reason = should_exclude_from_termbase(candidate.source_term)
    if excluded:
        return "reject", f"plan062 purge: {reason}", None
    concept = find_curated_concept(session, candidate.source_term)
    if concept is not None:
        return "apply", "plan062 purge: already curated", concept.id
    return "keep", "", None


def purge_stale_candidates(
    session: Session,
    *,
    dry_run: bool = True,
    job_id: str | None = None,
    actor_sub: str = "plan062-purge",
) -> dict[str, int]:
    stmt = select(DocumentTermCandidate).where(
        DocumentTermCandidate.status.in_(PURGE_STATUSES)
    )
    if job_id:
        stmt = stmt.where(DocumentTermCandidate.job_id == job_id)
    counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    extras: list[dict] = []
    for candidate in session.scalars(stmt).all():
        action, note, concept_id = classify_purge_action(session, candidate)
        counts[action] += 1
        extras.append(
            {
                "candidate_id": candidate.id,
                "source_term": candidate.source_term,
                "action": action,
                "note": note,
            }
        )
        if note:
            reason_counts[note] += 1
        if dry_run or action == "keep":
            continue
        if action == "reject":
            decide_candidate(
                session,
                candidate=candidate,
                actor_sub=actor_sub,
                action="reject",
                expected_version=candidate.version,
                note=note,
            )
        elif action == "apply":
            record_machine_decision(
                session,
                candidate=candidate,
                actor_sub=actor_sub,
                action="apply",
                note=note,
                concept_id=concept_id,
            )
    if reason_counts:
        print("purge_reasons", dict(reason_counts))
    if not dry_run:
        record_audit(
            session,
            actor_sub=actor_sub,
            action="workbench.candidate.purge",
            extra={
                "counts": dict(counts),
                "reasons": dict(reason_counts),
                "job_id": job_id,
            },
            note="plan062 purge stale candidates",
        )
    return dict(counts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge stale pending term candidates")
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--job-id", default=None)
    ap.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
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
        counts = purge_stale_candidates(
            session, dry_run=not args.apply, job_id=args.job_id
        )
        if args.apply:
            session.commit()
        mode = "apply" if args.apply else "dry-run"
        print(
            f"mode={mode} reject={counts.get('reject', 0)} "
            f"apply={counts.get('apply', 0)} keep={counts.get('keep', 0)}"
        )
    finally:
        session.close()
        reset_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

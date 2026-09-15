# SPDX-License-Identifier: MPL-2.0
"""PLAN-063b：领域准确度台账。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.glossary.candidate_rules import rules_version
from qyunslation.persist.models import DocumentTermCandidate, WorkbenchTranslationRun

DEFAULT_LEDGER = Path.home() / ".local/share/qyunslation/quality/ledger.jsonl"
SCREEN_GENERIC_RATIO_ALERT = 0.5


def ledger_path() -> Path:
    raw = (os.environ.get("QYUNSLATION_QUALITY_LEDGER") or "").strip()
    return Path(raw) if raw else DEFAULT_LEDGER


def _int_counts(excluded_stats: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, value in (excluded_stats or {}).items():
        if isinstance(value, int):
            counts[key] = value
    return counts


def classify_violations(session: Session, *, job_id: str) -> dict[str, int]:
    rows = session.scalars(
        select(DocumentTermCandidate).where(
            DocumentTermCandidate.job_id == job_id,
            DocumentTermCandidate.status == "violation",
        )
    ).all()
    true_miss = 0
    missing_alias = 0
    for row in rows:
        source = row.source_term or ""
        if source.lower().startswith(("anti-", "non-", "pre-")) or source.endswith(
            ("-50", "-75", "-90")
        ):
            missing_alias += 1
        else:
            true_miss += 1
    return {"true_violation": true_miss, "missing_alias": missing_alias}


def acceptance_rate(session: Session, *, tenant_id: str, project_id: str | None = None) -> float:
    stmt = select(DocumentTermCandidate).where(DocumentTermCandidate.tenant_id == tenant_id)
    if project_id:
        stmt = stmt.where(DocumentTermCandidate.project_id == project_id)
    rows = session.scalars(stmt).all()
    decided: dict[str, str] = {}
    for row in rows:
        if row.status not in {"approved", "rejected"}:
            continue
        decided[row.source_norm] = row.status
    approved = sum(1 for status in decided.values() if status == "approved")
    rejected = sum(1 for status in decided.values() if status == "rejected")
    total = approved + rejected
    return approved / total if total else 0.0


def screen_blindness(excluded_stats: dict[str, Any] | None) -> dict[str, Any]:
    counts = _int_counts(excluded_stats)
    origin = (excluded_stats or {}).get("screen_origin") or {}
    if not isinstance(origin, dict):
        origin = {}
    extracted = int((excluded_stats or {}).get("extracted_total") or sum(counts.values()) or 0)
    generic = int(counts.get("SCREEN_GENERIC", 0))
    ratio = generic / extracted if extracted else 0.0
    error_count = int(origin.get("error") or 0)
    cap_count = int(origin.get("cap") or 0)
    blind = error_count > 0 or cap_count > 0 or ratio > SCREEN_GENERIC_RATIO_ALERT
    return {
        "screen_generic_ratio": ratio,
        "screen_error_count": error_count,
        "screen_cap_count": cap_count,
        "screen_blind": blind,
        "extracted_total": extracted,
    }


def record_run(
    session: Session,
    *,
    run: WorkbenchTranslationRun,
    excluded_stats: dict[str, Any] | None = None,
    termbase_qa: dict[str, Any] | None = None,
    candidate_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stats = excluded_stats if excluded_stats is not None else (run.excluded_stats or {})
    summary = candidate_summary or {}
    violations = classify_violations(session, job_id=run.job_id)
    blind = screen_blindness(stats)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run.id,
        "job_id": run.job_id,
        "tenant_id": run.tenant_id,
        "rules_version": (stats or {}).get("rules_version") or rules_version(),
        "termbase_version": run.termbase_version,
        "prompt_version": (stats or {}).get("prompt_version") or "062-v1",
        "model_id": (stats or {}).get("model_id") or "",
        "pending": int(summary.get("pending") or 0),
        "applied": int(summary.get("applied") or 0),
        "approved": int(summary.get("approved") or 0),
        "rejected": int(summary.get("rejected") or 0),
        "violation": int(summary.get("violation") or 0),
        "true_violation": violations["true_violation"],
        "missing_alias": violations["missing_alias"],
        "termbase_qa_per_1k": float((termbase_qa or {}).get("finding_count") or 0),
        **blind,
    }
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def domain_metrics(
    session: Session,
    *,
    tenant_id: str,
    project_id: str | None = None,
    since: datetime | None = None,
) -> dict[str, Any]:
    stmt = select(WorkbenchTranslationRun).where(WorkbenchTranslationRun.tenant_id == tenant_id)
    if since is not None:
        stmt = stmt.where(WorkbenchTranslationRun.created_at >= since)
    runs = session.scalars(stmt).all()
    blinds = 0
    for run in runs:
        if screen_blindness(run.excluded_stats).get("screen_blind"):
            blinds += 1
    return {
        "runs": len(runs),
        "acceptance_rate": acceptance_rate(session, tenant_id=tenant_id, project_id=project_id),
        "screen_blind_runs": blinds,
        "rules_version": rules_version(),
    }

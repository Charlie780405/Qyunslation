# SPDX-License-Identifier: MPL-2.0
"""PLAN-073d：/next 译后术语候选抽取。"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.glossary.candidate_rules import classify_risk_by_rules, classify_term_type, should_exclude_from_termbase
from qyunslation.glossary.governance import normalize_source
from qyunslation.glossary.termbase import list_runtime_terms
from qyunslation.persist.models import DocumentTermCandidate, Job, PreflightRecord, TranslationRunRecord
from qyunslation.persist.repo import get_or_create_company_termbase_project

_EXTRACT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("drug", re.compile(r"\b[A-Z][a-z]{2,}(?:mab|nib|cept|umab|zumab)\b")),
    ("target", re.compile(r"\bIL[- ]?\d+[A-Za-zαβγ]?|JAK[- ]?\d+\b")),
    ("code", re.compile(r"\b(?:EASI|IGA|SCORAD|DLQI|PP-NRS|NRS|ADCT|POEM)(?:[- ]?\d+)?\b", re.I)),
    ("study_id", re.compile(r"\b[A-Z]{2,}\d{3,}[A-Z0-9-]*\b")),
    ("abbreviation", re.compile(r"\b[A-Z]{3,}(?:-[A-Z0-9]+)*\b")),
)
_MAX_CANDIDATES = 40


def _ensure_job(session: Session, *, run: TranslationRunRecord, preflight: PreflightRecord) -> Job:
    existing = session.scalar(
        select(Job).where(Job.storage_key == f"translation-run:{run.id}:{run.generation}").limit(1)
    )
    if existing is not None:
        return existing
    project = get_or_create_company_termbase_project(session, tenant_id=run.tenant_id)
    job = Job(
        id=str(uuid.uuid4()),
        project_id=project.id,
        source_sha256=preflight.source_sha256,
        status="completed",
        storage_key=f"translation-run:{run.id}:{run.generation}",
        provenance={"translation_run_id": run.id, "generation": run.generation},
    )
    session.add(job)
    session.flush()
    return job


def extract_candidates_from_text(
    session: Session,
    *,
    run: TranslationRunRecord,
    preflight: PreflightRecord,
    source_text: str,
    translated_text: str,
) -> list[DocumentTermCandidate]:
    profile = str((run.settings_snapshot or {}).get("profile") or "临床研究文档")
    known = {
        normalize_source(record.source_term)
        for record in list_runtime_terms(
            session,
            tenant_id=run.tenant_id,
            project_id=getattr(run, "project_id", None),
            document_profile=profile,
        )
    }
    job = _ensure_job(session, run=run, preflight=preflight)
    found: dict[str, tuple[str, str, str]] = {}
    for label, pattern in _EXTRACT_PATTERNS:
        for match in pattern.finditer(source_text or ""):
            token = match.group(0).strip()
            norm = normalize_source(token)
            if not norm or norm in known:
                continue
            excluded, _reason = should_exclude_from_termbase(token)
            if excluded:
                continue
            term_type = classify_term_type(token) if label == "abbreviation" else label
            risk = classify_risk_by_rules(token, term_type)
            found.setdefault(norm, (token, term_type, risk))
            if len(found) >= _MAX_CANDIDATES:
                break
        if len(found) >= _MAX_CANDIDATES:
            break
    project = get_or_create_company_termbase_project(session, tenant_id=run.tenant_id)
    rows: list[DocumentTermCandidate] = []
    for norm, (token, term_type, risk) in sorted(found.items()):
        existing = session.scalar(
            select(DocumentTermCandidate.id).where(
                DocumentTermCandidate.translation_run_id == run.id,
                DocumentTermCandidate.source_norm == norm,
            ).limit(1)
        )
        if existing:
            continue
        row = DocumentTermCandidate(
            id=str(uuid.uuid4()),
            job_id=job.id,
            translation_run_id=run.id,
            tenant_id=run.tenant_id,
            project_id=project.id,
            source_sha256=preflight.source_sha256,
            source_term=token,
            source_norm=norm,
            observed_target="",
            term_type=term_type,
            risk=risk,
            status="pending_admin" if risk == "high" else "pending",
            match_type="extracted",
            confidence=0.6,
            source_context=(source_text or "")[max(0, (source_text or "").find(token) - 40) :][:240],
            target_context=(translated_text or "")[:240],
        )
        session.add(row)
        rows.append(row)
    return rows

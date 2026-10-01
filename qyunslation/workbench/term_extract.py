# SPDX-License-Identifier: MPL-2.0
"""PLAN-074：/next 文献译后术语抽取、证据和审核候选落库。"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.glossary.candidate_rules import (
    classify_risk_by_rules,
    classify_term_type,
    rules_version,
    should_exclude_from_termbase,
)
from qyunslation.glossary.governance import normalize_source
from qyunslation.glossary.termbase import list_runtime_terms
from qyunslation.persist.candidate_repo import enqueue_candidate, load_rejected_suppress_index
from qyunslation.persist.models import (
    DocumentTermCandidate,
    Job,
    PreflightRecord,
    ReviewSegment,
    TranslationRunRecord,
)
from qyunslation.persist.repo import get_or_create_company_termbase_project
from qyunslation.structure.frontmatter import AFFILIATION, AUTHOR, classify_frontmatter_text
from qyunslation.structure.references import is_reference_entry, is_reference_heading, is_section_break
from qyunslation.glossary.term_morphology import is_rejected_source

_EXTRACT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("drug", re.compile(r"\b[A-Z][a-z]{2,}(?:mab|nib|cept|umab|zumab)\b")),
    ("target", re.compile(r"\b(?:IL[- ]?\d+[A-Za-zαβγ]?|JAK[- ]?\d+)\b", re.I)),
    ("code", re.compile(r"\b(?:EASI|IGA|SCORAD|DLQI|PP-NRS|NRS|ADCT|POEM)(?:[- ]?\d+)?\b", re.I)),
    ("study_id", re.compile(r"\b[A-Z]{2,}\d{3,}[A-Z0-9-]*\b")),
    ("abbreviation", re.compile(r"\b[A-Z]{3,}(?:-[A-Z0-9]+)*\b")),
    (
        "disease",
        re.compile(
            r"\b(?:atopic\s+dermatitis|vitiligo|psoriasis|eczema|asthma|urticaria|"
            r"dermatitis|alopecia\s+areata)\b",
            re.I,
        ),
    ),
    (
        "mechanism",
        re.compile(
            r"\b(?:melanocytes?|keratinocytes?|eosinophils?|cytokines?|biomarkers?|"
            r"(?:[A-Za-z0-9-]+\s+)?(?:receptor|pathway|signaling))\b",
            re.I,
        ),
    ),
)
EXTRACTION_RULE_VERSION = f"PLAN-074-v1+{rules_version()}"


def _paragraphs(text: str) -> list[tuple[str, int]]:
    """Preserve original offsets while treating PDF line breaks as review regions."""
    rows: list[tuple[str, int]] = []
    offset = 0
    for raw in (text or "").splitlines(keepends=True):
        value = raw.rstrip("\r\n")
        if value.strip():
            rows.append((value, offset))
        offset += len(raw)
    if not rows and (text or "").strip():
        rows.append((text, 0))
    return rows


def _exact_target_fragment(source_term: str, translated_text: str) -> str:
    """Return only a literal fragment present in output; never infer an observed translation."""
    match = re.search(re.escape(source_term), translated_text or "", re.I)
    return match.group(0) if match else ""


def discover_term_occurrences(source_text: str, translated_text: str) -> list[dict[str, Any]]:
    """Deterministically discover balanced medical candidates with complete locations.

    Model supplementation is a separate stage; this function is intentionally
    evidence-only and cannot invent a source term or target fragment.
    """
    found: dict[str, dict[str, Any]] = {}
    in_references = False
    for paragraph_no, (paragraph, base_offset) in enumerate(_paragraphs(source_text), start=1):
        if is_reference_heading(paragraph):
            in_references = True
            continue
        if in_references and is_section_break(paragraph):
            in_references = False
        if in_references or is_reference_entry(paragraph):
            continue
        frontmatter = classify_frontmatter_text(paragraph)
        if frontmatter.role in {AUTHOR, AFFILIATION}:
            continue
        for label, pattern in _EXTRACT_PATTERNS:
            for match in pattern.finditer(paragraph):
                token = match.group(0).strip()
                excluded, _reason = should_exclude_from_termbase(token)
                if excluded:
                    continue
                norm = normalize_source(token)
                if not norm:
                    continue
                term_type = classify_term_type(token) if label == "abbreviation" else label
                start = base_offset + match.start()
                end = base_offset + match.end()
                occurrence = {
                    "page_no": None,
                    "block_id": f"paragraph:{paragraph_no}",
                    "object_id": None,
                    "char_start": start,
                    "char_end": end,
                    "bbox": None,
                    "source_context": paragraph[:1000],
                    "target_context": (translated_text or "")[:1000],
                }
                row = found.setdefault(
                    norm,
                    {
                        "source_term": token,
                        "source_norm": norm,
                        "observed_target": _exact_target_fragment(token, translated_text),
                        "suggested_target": None,
                        "term_type": term_type,
                        "risk": classify_risk_by_rules(token, term_type),
                        "source_context": paragraph[:1000],
                        "target_context": (translated_text or "")[:1000],
                        "occurrences": [],
                        "extraction_metadata": {
                            "reason": f"deterministic:{label}",
                            "rule_version": EXTRACTION_RULE_VERSION,
                            "source_region": "translatable_content",
                        },
                    },
                )
                if not any(
                    item["char_start"] == start and item["char_end"] == end
                    for item in row["occurrences"]
                ):
                    row["occurrences"].append(occurrence)
    return sorted(found.values(), key=lambda item: item["source_norm"])


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


def sync_affiliation_segments_from_text(
    session: Session,
    *,
    run: TranslationRunRecord,
    preflight: PreflightRecord,
    source_text: str,
    translated_text: str,
) -> list[ReviewSegment]:
    """Create required affiliation review rows using page-order evidence.

    BabelDOC's paragraph trace is preferred when present; flattened PDF text is
    retained as a conservative fallback and never auto-confirms a segment.
    """
    job = _ensure_job(session, run=run, preflight=preflight)
    source_paragraphs = _paragraphs(source_text)
    target_paragraphs = _paragraphs(translated_text)
    created: list[ReviewSegment] = []
    for index, (source, _offset) in enumerate(source_paragraphs):
        if classify_frontmatter_text(source).role != AFFILIATION:
            continue
        block_id = f"paragraph:{index + 1}"
        existing = session.scalar(
            select(ReviewSegment).where(
                ReviewSegment.translation_run_id == run.id,
                ReviewSegment.generation == run.generation,
                ReviewSegment.role == AFFILIATION,
                ReviewSegment.block_id == block_id,
            )
        )
        if existing is not None:
            created.append(existing)
            continue
        machine = target_paragraphs[index][0] if index < len(target_paragraphs) else ""
        segment = ReviewSegment(
            job_id=job.id,
            translation_run_id=run.id,
            generation=run.generation,
            page_no=None,
            bbox=None,
            source_sha256=preflight.source_sha256,
            block_id=block_id,
            policy="HUMAN_REVIEW",
            role=AFFILIATION,
            source_text=source,
            machine_text=machine,
            status="pending",
            version=1,
        )
        session.add(segment)
        created.append(segment)
    session.flush()
    return created


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
    project = get_or_create_company_termbase_project(session, tenant_id=run.tenant_id)
    suppressed = load_rejected_suppress_index(
        session, tenant_id=run.tenant_id, project_id=project.id
    )
    rows: list[DocumentTermCandidate] = []
    for item in discover_term_occurrences(source_text, translated_text):
        if item["source_norm"] in known or is_rejected_source(item["source_term"], suppressed):
            continue
        row = enqueue_candidate(
            session,
            job=job,
            translation_run_id=run.id,
            tenant_id=run.tenant_id,
            project_id=project.id,
            source_term=item["source_term"],
            observed_target=item["observed_target"],
            suggested_target=item["suggested_target"],
            term_type=item["term_type"],
            risk=item["risk"],
            match_type="extracted",
            confidence=0.75,
            source_context=item["source_context"],
            target_context=item["target_context"],
            occurrences=item["occurrences"],
            extraction_metadata=item["extraction_metadata"],
        )
        rows.append(row)
    run.term_summary = {
        **dict(run.term_summary or {}),
        "extraction_status": "complete",
        "candidate_count": len(rows),
        "rule_version": EXTRACTION_RULE_VERSION,
    }
    return rows

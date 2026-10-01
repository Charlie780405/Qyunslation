# SPDX-License-Identifier: MPL-2.0
"""PLAN-073d：/next 译前术语 CSV 注入。"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from qyunslation.glossary.term_policy import compile_term_policy, policy_to_glossary
from qyunslation.glossary.termbase import resolve_runtime_terms, runtime_termbase_version
from qyunslation.pipeline.qa.pdf_inspect import read_pdf_facts
from qyunslation.persist.models import PreflightRecord, TranslationRunRecord


def _preflight_path(record: PreflightRecord) -> Path:
    import os

    root = Path(os.environ.get("QYUNSLATION_PREFLIGHT_ROOT") or "var/preflights").resolve()
    path = (root / record.storage_key).resolve()
    if root not in path.parents:
        raise ValueError("invalid preflight storage key")
    return path


def _source_text_for_preflight(preflight: PreflightRecord) -> str:
    try:
        path = _preflight_path(preflight)
    except Exception:
        return ""
    if path.suffix.casefold() == ".pdf":
        facts = read_pdf_facts(path)
        return facts.text if facts else ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:500_000]
    except OSError:
        return ""


def build_run_glossary_path(
    session: Session,
    *,
    run: TranslationRunRecord,
    preflight: PreflightRecord,
    run_dir: Path,
) -> tuple[str | None, dict[str, Any]]:
    """Return glossary CSV path and term policy metadata for settings snapshot."""
    settings = dict(run.settings_snapshot or {})
    profile = str(settings.get("profile") or preflight.metadata_json.get("recommended", {}).get("profile") or "临床研究文档")
    source_text = _source_text_for_preflight(preflight)
    matches = resolve_runtime_terms(
        session,
        tenant_id=run.tenant_id,
        project_id=getattr(run, "project_id", None),
        text=source_text,
        document_profile=profile,
    )
    version = runtime_termbase_version(
        session, tenant_id=run.tenant_id, project_id=getattr(run, "project_id", None)
    )
    policy = compile_term_policy(matches, termbase_version=version)
    hard_terms = policy_to_glossary(policy)
    if not hard_terms:
        return None, {"termbase_version": version, "injected_terms": 0}
    directory = run_dir / ".qyunslation-termbase"
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(
        json.dumps(hard_terms, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    glossary_path = directory / f"terms-{digest}.csv"
    if not glossary_path.exists():
        with glossary_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["source", "target"])
            writer.writerows(sorted(hard_terms.items()))
    return str(glossary_path.resolve()), {
        "termbase_version": version,
        "injected_terms": len(hard_terms),
        "glossary_path": str(glossary_path.resolve()),
    }

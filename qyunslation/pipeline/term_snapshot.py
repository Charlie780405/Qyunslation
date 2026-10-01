# SPDX-License-Identifier: MPL-2.0
"""PLAN-071h Task 5：任务级术语快照（可版本化、可哈希），QA 与检查器同源读取。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from qyunslation.glossary.candidate_rules import classify_risk_by_rules
from qyunslation.glossary.term_policy import compile_term_policy
from qyunslation.glossary.termbase import resolve_runtime_terms, runtime_termbase_version
from qyunslation.pipeline.qa.engine import QaFinding

SNAPSHOT_SCHEMA = "071h-term-snapshot-v1"
MAX_TERMS = 300


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    body = {k: v for k, v in snapshot.items() if k != "content_hash"}
    return _hash(body)


def build_term_snapshot(
    session: Session,
    *,
    tenant_id: str,
    project_id: str | None,
    source_text: str,
    src_lang: str = "en",
    tgt_lang: str = "zh",
) -> dict[str, Any]:
    matches = resolve_runtime_terms(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        text=source_text,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
    )
    version = runtime_termbase_version(session, tenant_id=tenant_id, project_id=project_id)
    policy = compile_term_policy(matches, termbase_version=version)
    terms: list[dict[str, Any]] = []
    for item in policy["terms"][:MAX_TERMS]:
        risk = classify_risk_by_rules(item["source_term"], item.get("term_type"))
        terms.append(
            {
                "concept_id": item["concept_id"],
                "source_term": item["source_term"],
                "preferred_target": item["preferred_target"],
                "term_type": item.get("term_type"),
                "do_not_translate": bool(item.get("do_not_translate")),
                "forbidden_targets": list(item.get("forbidden_targets") or []),
                "hard_constraint": bool(item.get("hard_constraint")),
                "risk": risk,
            }
        )
    snapshot: dict[str, Any] = {
        "status": "ready",
        "schema": SNAPSHOT_SCHEMA,
        "termbase_version": version,
        "match_count": len(policy["terms"]),
        "hard_constraints": sum(1 for t in terms if t["hard_constraint"]),
        "high_risk_terms": sum(1 for t in terms if t["risk"] == "high"),
        "terms": terms,
    }
    snapshot["content_hash"] = snapshot_hash(snapshot)
    return snapshot


def snapshot_is_consistent(snapshot: dict[str, Any] | None) -> bool:
    if not snapshot or snapshot.get("status") != "ready":
        return False
    return snapshot.get("content_hash") == snapshot_hash(snapshot)


def check_terms_in_translation(
    snapshot: dict[str, Any], translated_text: str
) -> list[QaFinding]:
    """与 RunDetail 检查器读同一快照；快照被篡改则报 blocker。"""
    if not snapshot_is_consistent(snapshot):
        return [
            QaFinding(
                category="consistency",
                severity="blocker",
                code="TERM_SNAPSHOT_INCONSISTENT",
                message="术语快照哈希与内容不一致，无法证明 QA 与检查器同源",
            )
        ]
    findings: list[QaFinding] = []
    text = translated_text or ""
    folded = text.casefold()
    for term in snapshot.get("terms") or []:
        if not term.get("hard_constraint"):
            continue
        high = term.get("risk") == "high"
        target = term["source_term"] if term.get("do_not_translate") else term.get("preferred_target") or ""
        for forbidden in term.get("forbidden_targets") or []:
            if forbidden and forbidden.casefold() in folded:
                findings.append(
                    QaFinding(
                        category="terminology",
                        severity="blocker",
                        code="TERM_FORBIDDEN_TARGET",
                        message=f"出现禁用译法：{forbidden}（术语 {term['source_term']}）",
                        evidence={"concept_id": term["concept_id"], "forbidden": forbidden},
                    )
                )
        if target and target.casefold() not in folded:
            findings.append(
                QaFinding(
                    category="terminology",
                    severity="blocker" if high else "warning",
                    code="TERM_HIGH_RISK_CONFLICT" if high else "TERM_TARGET_MISSING",
                    message=f"批准译名未出现：{term['source_term']} → {target}",
                    evidence={"concept_id": term["concept_id"], "expected": target},
                )
            )
    return findings

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-079 阶段 B：门禁与 QA 的只读基线（只输出聚合计数，不输出文档文字）。

回答四个问题（见 PLAN-079 §6 阶段 B、§10 的假设 H1–H3）：

* 已到达门禁的任务，各个门禁原因出现多少次；有多少任务**只因**未决术语被阻断（H2）。
* 未决术语候选按 状态 × 风险 × 类型 × 抽取来源 如何分布。
* `TEXT_ENCODING_ARTIFACT` 的锚点摘录属于哪一类码点（FFFD / C0 / C1 / mojibake）（H1）。
* 每个 `violation` 候选是否都有对应的当前 QA 条目，以及该条目是不是阻断（H3）。

    python3 scripts/qa/plan079_baseline.py [--tenant-id ID] [--out var/plan079]

只读：不写数据库，不导出术语原文或文档摘录；输出目录默认 var/plan079/（不入库）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_C0_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_C1_RE = re.compile(r"[\x80-\x9f]")
_MOJIBAKE_RE = re.compile(r"(?:Ã.|Â.|â(?:€™|€œ|€|€“|€”|€¦))")
# 大写拉丁扩展字母夹在大写字母之间，多半是葡/西语人名或地名（JOÃO、SÃO PAULO），不是 UTF-8 误解码。
_UPPER_NAME_RE = re.compile(r"(?<![a-zà-ÿ€])[A-Z]+[ÃÂ][A-Z]+(?![a-zà-ÿ])")
_TERM_QA_CODES = frozenset(
    {"TERM_HIGH_RISK_CONFLICT", "TERM_FORBIDDEN_TARGET", "TERM_TARGET_MISSING", "AD_TERM_MISSING"}
)
_FINAL_TERM_STATUSES = frozenset({"approved", "rejected", "applied"})


def classify_codepoints(text: str | None) -> list[str]:
    """Which detector families fire on this excerpt. A single excerpt can fire several."""
    raw = text or ""
    families: list[str] = []
    if "�" in raw:
        families.append("fffd")
    if _C0_RE.search(raw):
        families.append("c0")
    if _C1_RE.search(raw):
        families.append("c1")
    if _MOJIBAKE_RE.search(raw):
        families.append("mojibake_upper_name" if _looks_like_upper_name(raw) else "mojibake")
    return families or ["none"]


def _looks_like_upper_name(text: str) -> bool:
    """`Ã.` hit that has no `€` sequence and sits inside an all-capital word."""
    if "€" in text:
        return False
    return bool(_UPPER_NAME_RE.search(text))


def reconcile_violation(concept_id: str | None, qa_by_concept: dict[str, list[str]]) -> str:
    """matched_blocker | matched_warning | unmatched for one `violation` candidate."""
    if not concept_id:
        return "no_concept_id"
    severities = qa_by_concept.get(concept_id)
    if not severities:
        return "unmatched"
    return "matched_blocker" if "blocker" in severities else "matched_warning"


def _reason_prefix(metadata: dict[str, Any] | None) -> str:
    reason = str((metadata or {}).get("reason") or "")
    return reason.split(":", 1)[0][:32] or "(none)"


def build_report(session: Any, *, tenant_id: str | None = None) -> dict[str, Any]:
    from sqlalchemy import select

    from qyunslation.api.v1 import _gate_from
    from qyunslation.persist.models import DocumentTermCandidate, QaItem, TranslationRunRecord

    query = select(TranslationRunRecord).where(
        TranslationRunRecord.status == "gated", TranslationRunRecord.deleted_at.is_(None)
    )
    if tenant_id:
        query = query.where(TranslationRunRecord.tenant_id == tenant_id)
    runs = list(session.scalars(query))
    run_ids = [run.id for run in runs]

    candidates_by_run: dict[str, list[Any]] = {}
    if run_ids:
        for row in session.scalars(
            select(DocumentTermCandidate).where(DocumentTermCandidate.translation_run_id.in_(run_ids))
        ):
            candidates_by_run.setdefault(row.translation_run_id, []).append(row)
    qa_by_run: dict[str, list[Any]] = {}
    if run_ids:
        for row in session.scalars(
            select(QaItem).where(QaItem.run_id.in_(run_ids), QaItem.is_current.is_(True))
        ):
            qa_by_run.setdefault(row.run_id, []).append(row)

    reasons: Counter[str] = Counter()
    only_terms = released_by_new_rule = 0
    unresolved_breakdown: Counter[str] = Counter()
    encoding_families: Counter[str] = Counter()
    encoding_items = encoding_anchors = 0
    violation_outcome: Counter[str] = Counter()
    violations_total = 0

    for run in runs:
        candidates = candidates_by_run.get(run.id, [])
        unresolved = [c for c in candidates if c.status not in _FINAL_TERM_STATUSES]
        gate = _gate_from(run, [c.id for c in unresolved], None)
        reasons.update(gate["reasons"])
        if gate["reasons"] == ["unresolved_terms"]:
            only_terms += 1
        if "unresolved_terms" in gate["reasons"] and set(gate["reasons"]) == {"unresolved_terms"}:
            released_by_new_rule += 1
        for cand in unresolved:
            key = f"{cand.status}|{cand.risk}|{cand.term_type}|{_reason_prefix(cand.extraction_metadata)}"
            unresolved_breakdown[key] += 1

        items = qa_by_run.get(run.id, [])
        qa_by_concept: dict[str, list[str]] = {}
        for item in items:
            cid = (item.evidence_json or {}).get("concept_id")
            if item.code in _TERM_QA_CODES and cid:
                qa_by_concept.setdefault(str(cid), []).append(item.severity)
            if item.code == "TEXT_ENCODING_ARTIFACT":
                encoding_items += 1
                anchors = ((item.location_json or {}).get("anchors")) or []
                encoding_anchors += len(anchors)
                for anchor in anchors:
                    for family in classify_codepoints(anchor.get("excerpt")):
                        encoding_families[family] += 1
        for cand in candidates:
            if cand.status == "violation":
                violations_total += 1
                violation_outcome[reconcile_violation(cand.concept_id, qa_by_concept)] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gated_runs": len(runs),
        "gate_reasons": dict(reasons),
        "only_unresolved_terms": only_terms,
        "released_by_new_rule": released_by_new_rule,
        "unresolved_candidates_by_status_risk_type_source": dict(unresolved_breakdown.most_common()),
        "text_encoding_artifact": {
            "items": encoding_items,
            "anchors": encoding_anchors,
            "excerpt_families": dict(encoding_families),
            "note": "excerpt families only; whether the source PDF has the same hit needs the source text (stage B2)",
        },
        "violation_reconciliation": {"total": violations_total, **dict(violation_outcome)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PLAN-079 read-only gate baseline")
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--out", default="var/plan079")
    args = parser.parse_args()

    from sqlalchemy.orm import Session

    from qyunslation.persist.db import get_database_url, init_engine

    url = get_database_url()
    if not url:
        print("FAIL: QYUNSLATION_DATABASE_URL required", file=sys.stderr)
        return 1
    engine = init_engine(url)
    with Session(engine) as session:
        report = build_report(session, tenant_id=args.tenant_id)
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"baseline-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nwritten: {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-079 E2/E3：影子期差异报告（只读，只输出聚合与任务 ID 前缀，不含术语原文）。

数据源是 QA 轮次写进 ``run.term_summary.gate_shadow`` 的记录（``QYUNSLATION_TERM_GATE_MODE=shadow`` 时产生）。
记录里只有“由术语策略引起”的原因：旧口径为 unresolved_terms，新口径为 TERM_REVIEW_REQUIRED/violation 补发造成的 qa_blockers；
门禁的其余部分在两种口径下相同，不重复记录。
重点回答：哪些任务“旧口径阻断、新口径放行”（必须逐个抽查，确认没有真实高风险缺陷被放过），
以及新口径多出了多少 ``TERM_REVIEW_REQUIRED`` / ``violation`` 补发。

    python3 scripts/qa/plan079_shadow_report.py [--tenant-id ID] [--limit 50]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def summarize(runs: list[Any], *, limit: int = 50) -> dict[str, Any]:
    legacy_reasons: Counter[str] = Counter()
    new_reasons: Counter[str] = Counter()
    released: list[str] = []
    newly_blocked: list[str] = []
    review = violations = overflow = recorded = 0
    for run in runs:
        shadow = (run.term_summary or {}).get("gate_shadow")
        if not shadow:
            continue
        recorded += 1
        legacy, new = list(shadow.get("legacy_term_reasons") or []), list(shadow.get("new_term_reasons") or [])
        legacy_reasons.update(legacy)
        new_reasons.update(new)
        review += int(shadow.get("review_required") or 0)
        violations += int(shadow.get("violation_findings") or 0)
        overflow += int(shadow.get("review_overflow") or 0)
        if legacy and not new:
            released.append(run.id[:8])
        if not legacy and new:
            newly_blocked.append(run.id[:8])
    return {
        "runs_with_shadow_record": recorded,
        "legacy_term_reasons": dict(legacy_reasons),
        "new_term_reasons": dict(new_reasons),
        "released_by_new_rule": len(released),
        "newly_blocked_by_new_rule": len(newly_blocked),
        "review_required_total": review,
        "violation_findings_total": violations,
        "review_overflow_total": overflow,
        "inspect_released_runs": released[:limit],
        "inspect_newly_blocked_runs": newly_blocked[:limit],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PLAN-079 shadow-period difference report")
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from qyunslation.persist.db import get_database_url, init_engine
    from qyunslation.persist.models import TranslationRunRecord

    url = get_database_url()
    if not url:
        print("FAIL: QYUNSLATION_DATABASE_URL required", file=sys.stderr)
        return 1
    engine = init_engine(url)
    with Session(engine) as session:
        query = select(TranslationRunRecord).where(TranslationRunRecord.deleted_at.is_(None))
        if args.tenant_id:
            query = query.where(TranslationRunRecord.tenant_id == args.tenant_id)
        print(json.dumps(summarize(list(session.scalars(query)), limit=args.limit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

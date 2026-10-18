#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-078a：QA 阻断诊断（只读）。

Answers "why do translations keep stopping at QA?" from the run ledger without touching it:
the session is read-only, nothing is written, and only counts, codes and enum-like columns
are reported (never file names, text, or evidence bodies).

    QYUNSLATION_DATABASE_URL=... python3 scripts/plan078-qa-diagnose.py --days 30
    python3 scripts/plan078-qa-diagnose.py --days 90 --json > diagnose.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXECUTING = {"queued", "scanning", "translating", "rendering"}
GATE_QUALITY = {"qa_blocked", "review_ready", "qa_degraded", "qa_unavailable", "changes_requested"}
DIMENSIONS = ("format", "direction", "domain", "model", "classification", "rule_version")


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _is_located(item: Any) -> bool:
    evidence = item.evidence_json or {}
    return bool(item.object_id) or any(key in evidence for key in ("page", "pages", "object_id"))


def collect(session: Any, *, days: int, now: datetime | None = None) -> dict[str, Any]:
    from sqlalchemy import select

    from qyunslation.persist.models import PreflightRecord, QaItem, TranslationRunRecord

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    rows = session.execute(
        select(TranslationRunRecord, PreflightRecord.source_format).join(
            PreflightRecord, PreflightRecord.id == TranslationRunRecord.preflight_id, isouter=True
        )
    ).all()
    runs = [(run, fmt) for run, fmt in rows if (_aware(run.created_at) or now) >= cutoff]
    run_meta: dict[str, dict[str, str]] = {}
    for run, fmt in runs:
        settings = run.settings_snapshot or {}
        run_meta[run.id] = {
            "format": fmt or "?",
            "direction": run.direction or "?",
            "domain": str(settings.get("domain_profile") or "general"),
            "model": run.model_profile_id or "?",
            "classification": run.document_classification or "?",
        }

    generation_of = {run.id: run.generation for run, _ in runs}
    items = [
        item
        for item in session.scalars(select(QaItem).where(QaItem.severity.in_(("blocker", "unavailable"))))
        if generation_of.get(item.run_id) == item.generation  # only the run's current generation
    ]

    by_state = Counter(f"{run.status}/{run.quality_state or 'draft'}" for run, _ in runs)
    reached_qa = [run for run, _ in runs if (run.quality_state or "draft") != "draft"]
    blocked = [run for run in reached_qa if run.quality_state == "qa_blocked"]
    unavailable = [run for run in reached_qa if run.quality_state == "qa_unavailable"]

    codes: dict[str, dict[str, Any]] = {}
    for item in items:
        entry = codes.setdefault(
            item.code,
            {"severity": item.severity, "items": 0, "runs": set(), "located": 0,
             **{dim: Counter() for dim in DIMENSIONS}},
        )
        entry["items"] += 1
        entry["runs"].add(item.run_id)
        entry["located"] += 1 if _is_located(item) else 0
        meta = run_meta[item.run_id]
        for dim in DIMENSIONS:
            if dim == "rule_version":
                value = (item.evidence_json or {}).get("rule_version") or "(none)"
            else:
                value = meta[dim]
            entry[dim][str(value)] += 1

    code_rows = []
    for code, entry in sorted(codes.items(), key=lambda kv: (-len(kv[1]["runs"]), kv[0])):
        code_rows.append(
            {
                "code": code,
                "severity": entry["severity"],
                "items": entry["items"],
                "runs": len(entry["runs"]),
                "located_share": round(entry["located"] / entry["items"], 3) if entry["items"] else 0.0,
                **{dim: dict(entry[dim].most_common()) for dim in DIMENSIONS},
            }
        )

    # Rows the plan treats as inconsistent state rather than as quality problems.
    interrupted_at_gate = [
        run for run, _ in runs
        if run.status == "interrupted" and (run.quality_state or "draft") in GATE_QUALITY
    ]
    translating_at_gate = [
        run for run, _ in runs
        if run.status == "translating" and (run.quality_state or "draft") in GATE_QUALITY
    ]
    stuck_checking = [
        run for run, _ in runs
        if run.status == "gated" and (run.quality_state or "draft") == "draft"
        and (_aware(run.updated_at) or now) < now - timedelta(hours=1)
    ]
    hours = [
        ((_aware(run.completed_at) - _aware(run.created_at)).total_seconds() / 3600)
        for run, _ in runs
        if run.quality_state == "approved" and run.completed_at and run.created_at
    ]
    return {
        "window_days": days,
        "generated_at": now.isoformat(),
        "runs": len(runs),
        "by_status_quality": dict(by_state.most_common()),
        "reached_qa": len(reached_qa),
        "qa_blocked": len(blocked),
        "qa_unavailable": len(unavailable),
        "qa_blocked_rate": round(len(blocked) / len(reached_qa), 3) if reached_qa else None,
        "qa_unavailable_rate": round(len(unavailable) / len(reached_qa), 3) if reached_qa else None,
        "codes": code_rows,
        "inconsistent": {
            "interrupted_while_at_gate": len(interrupted_at_gate),
            "translating_while_at_gate": len(translating_at_gate),
            "checking_for_over_1h": len(stuck_checking),
        },
        "median_hours_created_to_approved": round(statistics.median(hours), 2) if hours else None,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"QA 诊断（近 {report['window_days']} 天，{report['runs']} 个任务，生成于 {report['generated_at']}）",
        "",
        "状态/质量分布：",
    ]
    lines += [f"  {key}: {count}" for key, count in report["by_status_quality"].items()]
    lines += [
        "",
        f"进入 QA 的任务 {report['reached_qa']}：阻断 {report['qa_blocked']}（{report['qa_blocked_rate']}），"
        f"检查未完成 {report['qa_unavailable']}（{report['qa_unavailable_rate']}）",
        "",
        "阻断/未完成代码（按受影响任务数）：",
    ]
    for row in report["codes"]:
        lines.append(
            f"  {row['code']} [{row['severity']}] 任务 {row['runs']} 条目 {row['items']} 可定位 {row['located_share']:.0%}"
        )
        for dim in DIMENSIONS:
            lines.append(f"      {dim}: {row[dim]}")
    inconsistent = report["inconsistent"]
    lines += [
        "",
        "状态不一致（需要回填或人工确认，本脚本不修改）：",
        f"  已在闸门却被心跳标记为中断：{inconsistent['interrupted_while_at_gate']}",
        f"  已在闸门却仍是 translating：{inconsistent['translating_while_at_gate']}",
        f"  检查超过 1 小时未出结果：{inconsistent['checking_for_over_1h']}",
        f"批准用时中位数（小时）：{report['median_hours_created_to_approved']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--database-url", default=None, help="defaults to QYUNSLATION_DATABASE_URL")
    args = parser.parse_args(argv)

    from sqlalchemy import event, text
    from sqlalchemy.orm import Session

    from qyunslation.persist.db import get_database_url, init_engine

    url = get_database_url(args.database_url)
    if not url:
        print("FAIL: QYUNSLATION_DATABASE_URL (or --database-url) is required", file=sys.stderr)
        return 2
    engine = init_engine(url)

    @event.listens_for(engine, "connect")
    def _read_only(dbapi_connection, _record):  # pragma: no cover - driver specific
        cursor = dbapi_connection.cursor()
        try:
            if engine.dialect.name == "sqlite":
                cursor.execute("PRAGMA query_only = ON")
            else:
                cursor.execute("SET default_transaction_read_only = on")
        finally:
            cursor.close()

    with Session(engine) as session:
        session.execute(text("SELECT 1"))
        report = collect(session, days=args.days)
        session.rollback()
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

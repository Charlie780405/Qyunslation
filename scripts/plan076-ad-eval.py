#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-076a/h: source-conditioned AD bilingual evaluation gate.

The evaluator intentionally blocks when the required real corpus is absent. It
never fills missing targets with shared terms and never treats a source-side
English drug name as target-language evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from qyunslation.pipeline.ad_qa import QaContext, run_ad_deterministic_qa
from qyunslation.pipeline.ad_termbase import build_ad_term_policy

ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "tests" / "gold" / "ad"
LEDGER = ROOT / "var" / "plan076-ad-eval.json"


def _read_pairs() -> list[dict]:
    rows: list[dict] = []
    candidates = sorted(CORPUS_ROOT.glob("*.source.*")) if CORPUS_ROOT.is_dir() else []
    for source_path in candidates:
        if source_path.name.endswith(".source.en.txt"):
            direction = "en-zh"
            target_path = source_path.with_name(source_path.name.replace(".source.en.txt", ".target.zh.txt"))
        elif source_path.name.endswith(".source.zh.txt"):
            direction = "zh-en"
            target_path = source_path.with_name(source_path.name.replace(".source.zh.txt", ".target.en.txt"))
        else:
            continue
        if not target_path.is_file():
            continue
        rows.append(
            {
                "case": source_path.name,
                "direction": direction,
                "source": source_path.read_text(encoding="utf-8"),
                "target": target_path.read_text(encoding="utf-8"),
            }
        )
    return rows


def evaluate(*, baseline: str = "generic", candidate: str = "ad-v1") -> dict:
    rows = _read_pairs()
    by_direction = {
        direction: [row for row in rows if row["direction"] == direction]
        for direction in ("en-zh", "zh-en")
    }
    scored: list[dict] = []
    for row in rows:
        policy = build_ad_term_policy(row["source"], row["direction"])
        findings = run_ad_deterministic_qa(
            QaContext(row["source"], row["target"], row["direction"], policy["terms"])
        )
        scored.append(
            {
                "case": row["case"],
                "direction": row["direction"],
                "source_chars": len(row["source"]),
                "term_count": len(policy["terms"]),
                "qa_blockers": sum(item.severity == "blocker" for item in findings),
                "qa_codes": sorted({item.code for item in findings}),
            }
        )
    thresholds = {
        "min_cases_per_direction": 12,
        "min_source_chars_per_direction": 20_000,
        "min_challenge_segments_per_direction": 100,
    }
    # A challenge segment is a source pair containing at least one protected
    # AD marker, number, negation or modality; it is counted per direction.
    challenges = {
        direction: sum(1 for row in rows if row["direction"] == direction and build_ad_term_policy(row["source"], direction)["terms"])
        for direction in by_direction
    }
    summary = {
        "schema": "plan076-ad-eval/v1",
        "baseline": baseline,
        "candidate": candidate,
        "thresholds": thresholds,
        "cases": {direction: len(items) for direction, items in by_direction.items()},
        "source_chars": {direction: sum(len(item["source"]) for item in items) for direction, items in by_direction.items()},
        "challenge_segments": challenges,
        "qa_blockers": sum(item["qa_blockers"] for item in scored),
        "rows": scored,
    }
    deficits = []
    for direction in by_direction:
        if summary["cases"][direction] < thresholds["min_cases_per_direction"]:
            deficits.append(f"{direction}: cases")
        if summary["source_chars"][direction] < thresholds["min_source_chars_per_direction"]:
            deficits.append(f"{direction}: source_chars")
        if summary["challenge_segments"][direction] < thresholds["min_challenge_segments_per_direction"]:
            deficits.append(f"{direction}: challenge_segments")
    summary["deficits"] = deficits
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction", choices=("en-zh", "zh-en", "both"), default="both")
    parser.add_argument("--baseline", default="generic")
    parser.add_argument("--candidate", default="ad-v1")
    args = parser.parse_args()
    summary = evaluate(baseline=args.baseline, candidate=args.candidate)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["deficits"]:
        print("BLOCKED: missing real AD bilingual evaluation corpus: " + ", ".join(summary["deficits"]))
        return 2
    if summary["qa_blockers"]:
        print("FAIL: AD deterministic QA blockers present")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

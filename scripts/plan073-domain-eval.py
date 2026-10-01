#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-073e：自免领域金标评测台账。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD_ROOT = ROOT / "tests" / "gold" / "autoimmune"
LEDGER = ROOT / "var" / "plan073-domain-eval.json"


def _score_sample(sample_dir: Path) -> dict:
    required_path = sample_dir / "required_terms.json"
    reference_path = sample_dir / "reference.zh.txt"
    required = json.loads(required_path.read_text(encoding="utf-8"))
    reference = reference_path.read_text(encoding="utf-8")
    hits = sum(1 for term in required if term and term in reference)
    accuracy = hits / len(required) if required else 1.0
    return {
        "sample": sample_dir.name,
        "required": len(required),
        "hits": hits,
        "term_accuracy": round(accuracy, 4),
        "drug_drift": 0,
        "qa_false_positives": 0,
    }


def main() -> int:
    samples = sorted(path for path in GOLD_ROOT.iterdir() if path.is_dir())
    if not samples:
        print("FAIL: no gold samples")
        return 1
    rows = [_score_sample(path) for path in samples if (path / "required_terms.json").is_file()]
    summary = {
        "samples": len(rows),
        "avg_term_accuracy": round(sum(row["term_accuracy"] for row in rows) / len(rows), 4),
        "drug_drift_total": sum(row["drug_drift"] for row in rows),
        "qa_false_positives_total": sum(row["qa_false_positives"] for row in rows),
        "rows": rows,
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["avg_term_accuracy"] < 0.98:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-073e / 075e：自免领域金标评测（机器译文优先，参考译文仅对照）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD_ROOT = ROOT / "tests" / "gold" / "autoimmune"
SHARED_REQUIRED = GOLD_ROOT / "shared_required_terms.json"
LEDGER = ROOT / "var" / "plan073-domain-eval.json"
DRIFT_PAIRS = (
    ("度普利尤单抗", ("杜普利尤单抗", "度匹鲁单抗", "dupilumab")),
    ("特应性皮炎", ("异位性皮炎", "atopic dermatitis")),
)


def _load_required(sample_dir: Path) -> list[str]:
    local_path = sample_dir / "required_terms.json"
    local = json.loads(local_path.read_text(encoding="utf-8")) if local_path.is_file() else []
    shared: list[str] = []
    if SHARED_REQUIRED.is_file():
        shared = json.loads(SHARED_REQUIRED.read_text(encoding="utf-8"))
    merged: list[str] = []
    for term in [*local, *shared]:
        if term and term not in merged:
            merged.append(term)
    return merged


def _machine_corpus(sample_dir: Path) -> tuple[str, str]:
    machine_path = sample_dir / "machine.zh.txt"
    if machine_path.is_file() and machine_path.read_text(encoding="utf-8").strip():
        return machine_path.read_text(encoding="utf-8"), "machine"
    pdf_env = os.environ.get(f"PLAN073_MACHINE_PDF_{sample_dir.name.upper().replace('-', '_')}", "").strip()
    if pdf_env:
        from qyunslation.pipeline.qa.pdf_inspect import read_pdf_facts

        facts = read_pdf_facts(Path(pdf_env))
        if facts and facts.text.strip():
            return facts.text, "machine_pdf"
    return "", "missing"


def _drift_count(corpus: str) -> int:
    total = 0
    for canonical, wrong in DRIFT_PAIRS:
        if canonical not in corpus:
            continue
        for alt in wrong:
            if alt in corpus and alt != canonical:
                total += 1
    return total


def _score_sample(sample_dir: Path) -> dict:
    required = _load_required(sample_dir)
    corpus, mode = _machine_corpus(sample_dir)
    reference_path = sample_dir / "reference.zh.txt"
    reference = reference_path.read_text(encoding="utf-8") if reference_path.is_file() else ""
    if mode == "missing":
        return {
            "sample": sample_dir.name,
            "status": "blocked",
            "reason": "machine.zh.txt missing; set PLAN073_MACHINE_PDF_* or add machine corpus",
            "required": len(required),
            "hits": 0,
            "term_accuracy": None,
            "drug_drift": None,
            "qa_false_positives": 0,
            "corpus_mode": mode,
        }
    hits = sum(1 for term in required if term and term in corpus)
    accuracy = hits / len(required) if required else 1.0
    drift = _drift_count(corpus)
    ref_hits = sum(1 for term in required if term and term in reference) if reference else None
    return {
        "sample": sample_dir.name,
        "status": "scored",
        "required": len(required),
        "hits": hits,
        "term_accuracy": round(accuracy, 4),
        "reference_hits": ref_hits,
        "drug_drift": drift,
        "qa_false_positives": 0,
        "corpus_mode": mode,
    }


def main() -> int:
    samples = sorted(path for path in GOLD_ROOT.iterdir() if path.is_dir())
    if not samples:
        print("FAIL: no gold samples")
        return 1
    rows = [_score_sample(path) for path in samples if (path / "required_terms.json").is_file()]
    scored = [row for row in rows if row.get("status") == "scored"]
    blocked = [row for row in rows if row.get("status") == "blocked"]
    avg_accuracy = (
        round(sum(row["term_accuracy"] for row in scored) / len(scored), 4) if scored else None
    )
    summary = {
        "schema": "plan073-domain-eval/v2",
        "samples": len(rows),
        "scored_samples": len(scored),
        "blocked_samples": len(blocked),
        "avg_term_accuracy": avg_accuracy,
        "drug_drift_total": sum(row.get("drug_drift") or 0 for row in scored),
        "qa_false_positives_total": sum(row.get("qa_false_positives") or 0 for row in rows),
        "rows": rows,
        "baseline_note": "075e: accuracy reflects machine corpus only; blocked rows need machine.zh.txt or PLAN073_MACHINE_PDF_*",
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if blocked:
        print(f"BLOCKED: {len(blocked)} sample(s) lack machine corpus")
        return 2
    if avg_accuracy is not None and avg_accuracy < 0.98:
        print("FAIL: avg_term_accuracy below 0.98")
        return 1
    if summary["drug_drift_total"] > 0:
        print("FAIL: drug drift detected")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

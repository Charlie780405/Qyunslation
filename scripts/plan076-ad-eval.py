#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-076a/h: source-conditioned AD bilingual evaluation gate.

The evaluator intentionally blocks when the required real corpus is absent. It
never fills missing targets with shared terms and never treats a source-side
English drug name as target-language evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from qyunslation.pipeline.ad_qa import QaContext, run_ad_deterministic_qa
from qyunslation.pipeline.ad_termbase import build_ad_term_policy

ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = Path(os.environ.get("PLAN076_AD_CORPUS_ROOT") or ROOT / "tests" / "gold" / "ad")
LEDGER = ROOT / "var" / "plan076-ad-eval.json"
MANIFEST_NAME = "manifest.json"
REQUIRED_CASE_FIELDS = {
    "case_id",
    "direction",
    "document_profile",
    "source_ref",
    "reference_ref",
    "source_sha256",
    "reference_sha256",
    "annotations_ref",
    "license",
    "is_locked_test",
}
ALLOWED_DIRECTIONS = {"en-zh", "zh-en"}
ALLOWED_DOCUMENT_PROFILES = {"医学研究文献", "临床研究文档"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_ref(root: Path, ref: object) -> Path | None:
    if not isinstance(ref, str) or not ref.strip():
        return None
    candidate = (root / ref).resolve()
    if root.resolve() not in candidate.parents:
        return None
    return candidate


def check_corpus(corpus_root: Path = CORPUS_ROOT, *, direction: str = "both") -> dict:
    """Validate the manifest without exposing source, reference, or annotation text."""
    root = Path(corpus_root)
    manifest_path = root / MANIFEST_NAME
    errors: list[str] = []
    rows: list[dict] = []
    if not manifest_path.is_file():
        return {
            "valid": False,
            "manifest": False,
            "cases": 0,
            "errors": ["manifest_missing"],
            "rows": rows,
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "valid": False,
            "manifest": True,
            "cases": 0,
            "errors": ["manifest_invalid_json"],
            "rows": rows,
        }
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(cases, list):
        return {
            "valid": False,
            "manifest": True,
            "cases": 0,
            "errors": ["cases_not_list"],
            "rows": rows,
        }
    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"case[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix}:not_object")
            continue
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        if missing:
            errors.append(f"{prefix}:missing:{','.join(missing)}")
            continue
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in seen_ids:
            errors.append(f"{prefix}:duplicate_or_empty_case_id")
        seen_ids.add(case_id)
        item_direction = str(case.get("direction") or "")
        if item_direction not in ALLOWED_DIRECTIONS:
            errors.append(f"{prefix}:direction")
        if str(case.get("document_profile") or "") not in ALLOWED_DOCUMENT_PROFILES:
            errors.append(f"{prefix}:document_profile")
        if str(case.get("license") or "") != "public-or-internal-approved":
            errors.append(f"{prefix}:license")
        if case.get("is_locked_test") is not True:
            errors.append(f"{prefix}:not_locked_test")
        source_path = _safe_ref(root, case.get("source_ref"))
        reference_path = _safe_ref(root, case.get("reference_ref"))
        annotation_path = _safe_ref(root, case.get("annotations_ref"))
        if not source_path or not source_path.is_file():
            errors.append(f"{prefix}:source_missing_or_unsafe")
        if not reference_path or not reference_path.is_file():
            errors.append(f"{prefix}:reference_missing_or_unsafe")
        if not annotation_path or not annotation_path.is_file():
            errors.append(f"{prefix}:annotations_missing_or_unsafe")
        if source_path and source_path.is_file() and str(case.get("source_sha256")) != _sha256(source_path):
            errors.append(f"{prefix}:source_hash")
        if reference_path and reference_path.is_file() and str(case.get("reference_sha256")) != _sha256(reference_path):
            errors.append(f"{prefix}:reference_hash")
        if annotation_path and annotation_path.is_file():
            try:
                annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
                if not isinstance(annotations, dict):
                    errors.append(f"{prefix}:annotations_not_object")
            except (OSError, UnicodeError, json.JSONDecodeError):
                errors.append(f"{prefix}:annotations_invalid_json")
        if item_direction == direction or direction == "both":
            rows.append({"case_id": case_id, "direction": item_direction})
    return {
        "valid": not errors,
        "manifest": True,
        "cases": len(rows),
        "errors": sorted(set(errors)),
        "rows": rows,
    }


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


def evaluate(*, baseline: str = "generic", candidate: str = "ad-v1", direction: str = "both") -> dict:
    rows = _read_pairs()
    if direction != "both":
        rows = [row for row in rows if row["direction"] == direction]
    directions = ("en-zh", "zh-en") if direction == "both" else (direction,)
    by_direction = {
        item_direction: [row for row in rows if row["direction"] == item_direction]
        for item_direction in directions
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
        "direction": direction,
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
    parser.add_argument("--check-corpus", action="store_true")
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    corpus_check = check_corpus(direction=args.direction)
    if args.check_corpus:
        corpus_check["direction"] = args.direction
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps({"schema": "plan076-ad-corpus-check/v1", **corpus_check}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(corpus_check, ensure_ascii=False, indent=2))
        if not corpus_check["valid"]:
            print("BLOCKED: AD corpus manifest contract incomplete: " + ", ".join(corpus_check["errors"]))
            return 2
        return 0
    summary = evaluate(baseline=args.baseline, candidate=args.candidate, direction=args.direction)
    summary["corpus_contract"] = corpus_check
    if not corpus_check["valid"]:
        summary["deficits"].append("corpus_contract")
    if args.baseline_only:
        summary["mode"] = "baseline-only"
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

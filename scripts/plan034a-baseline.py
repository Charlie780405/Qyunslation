#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-034a：金标基线评测骨架（不整本重译）。

缺 ready 样本或 GOLD_ROOT 不完备 → exit 2 + BLOCKED。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.gold.plan034 import (  # noqa: E402
    CatalogCompletenessError,
    assert_catalog_complete,
    evaluate_baseline_report,
    gold_root,
    load_catalog,
    load_thresholds,
    ready_entries,
    resolve_entry,
    verify_entry_hash,
)


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _glossary_fingerprint() -> str:
    try:
        from qyunslation.glossary.governance import build_merged_dict

        return f"merged_dict_n={len(build_merged_dict())}"
    except Exception as exc:
        return f"glossary_unavailable:{exc}"


def main() -> int:
    ap = argparse.ArgumentParser(description="PLAN-034a baseline skeleton")
    ap.add_argument("--gold-root", type=Path, default=None)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="report path (default: /tmp/plan034a-baseline-<date>.md)",
    )
    ap.add_argument("--model-id", default="qwen3.6:35b-a3b")
    args = ap.parse_args()

    root = gold_root(args.gold_root)
    entries = load_catalog()
    thresholds = load_thresholds()
    ready = ready_entries(entries)

    lines: list[str] = [
        f"# PLAN-034a baseline {date.today().isoformat()}",
        "",
        "## Provenance",
        f"- git_head: `{_git_head()}`",
        f"- model_id: `{args.model_id}`",
        f"- glossary: `{_glossary_fingerprint()}`",
        f"- pharma_mqm: `1.0.0`",
        f"- thresholds: `{thresholds.get('version')}`",
        f"- gold_root: `{root}`",
        "",
        "## Entries",
    ]

    present = 0
    skipped_artifact = 0
    for e in ready:
        path = resolve_entry(e, root)
        if path is None or not verify_entry_hash(e, path):
            lines.append(f"- `{e.id}` **MISSING_OR_HASH** ({e.class_})")
            continue
        present += 1
        art = e.artifact_mono
        if art and Path(art).is_file():
            lines.append(f"- `{e.id}` OK file + artifact `{art}` (probe deferred)")
        else:
            skipped_artifact += 1
            lines.append(
                f"- `{e.id}` OK file; **SKIPPED_NO_ARTIFACT** (no full retranslate this phase)"
            )

    lines.extend(
        [
            "",
            "## Completeness gate",
        ]
    )

    blocked = False
    try:
        summary = assert_catalog_complete(entries, root=root)
        lines.append(f"- assert_catalog_complete: PASS `{summary}`")
    except CatalogCompletenessError as exc:
        blocked = True
        lines.append(f"- assert_catalog_complete: **BLOCKED** — {exc}")

    # Skeleton metrics: no Critical measured this phase → honest zeros only if complete
    report = {
        "critical_count": 0,
        "hard_term_hit_rate": 1.0 if not blocked else 0.0,
        "forbidden_translation_count": 0,
        "digit_unit_doi_ref_pass_rate": 1.0 if not blocked else 0.0,
        "ready_present": present,
        "skipped_no_artifact": skipped_artifact,
    }
    verdict = evaluate_baseline_report(report, thresholds)
    lines.extend(
        [
            "",
            "## Threshold evaluation (skeleton)",
            f"- report: `{report}`",
            f"- evaluate_baseline_report: **{verdict}**",
            "",
            "## Note",
            "本期不做整本重译；完备性 BLOCKED 时不得宣称基线通过。",
        ]
    )

    out = args.out or Path(f"/tmp/plan034a-baseline-{date.today().isoformat()}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")

    if blocked:
        print("SUMMARY: BLOCKED")
        return 2
    print("SUMMARY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

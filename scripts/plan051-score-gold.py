#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-051b：读 run-manifest 批次，写出 full-retranslate MQM 报告。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.gold.plan051_run import plan051_out_root  # noqa: E402
from qyunslation.gold.plan051_score import (  # noqa: E402
    Plan051ScoreError,
    evaluate_or_fail,
    load_manifests_from_out_root,
    score_manifests,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="PLAN-051b MQM scorer")
    ap.add_argument("--out-root", type=Path, default=None)
    ap.add_argument("--manifests-json", type=Path, default=None, help="夹具：manifest 数组")
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--reject-if", type=Path, default=None, help="若该 JSON 为 skeleton 则 FAIL")
    ap.add_argument("--model-id", default="qwen3.6:35b-a3b")
    args = ap.parse_args()

    if args.reject_if is not None:
        try:
            rep = json.loads(args.reject_if.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"SUMMARY: FAIL — cannot read {args.reject_if}: {exc}", file=sys.stderr)
            return 1
        try:
            evaluate_or_fail(rep if isinstance(rep, dict) else {})
        except Plan051ScoreError as exc:
            print(f"SUMMARY: FAIL — {exc}")
            return 1
        # 若不是 skeleton 但仍要拒非 full：evaluate_or_fail 已查 mode
        print("SUMMARY: PASS reject-check")
        return 0

    if args.manifests_json is not None:
        raw = json.loads(args.manifests_json.read_text(encoding="utf-8"))
        manifests = raw if isinstance(raw, list) else raw.get("manifests") or []
    else:
        root = plan051_out_root(args.out_root)
        manifests = load_manifests_from_out_root(root)

    try:
        report = score_manifests(manifests, model_id=args.model_id)
        verdict = evaluate_or_fail(report)
    except Plan051ScoreError as exc:
        print(f"SUMMARY: FAIL — {exc}", file=sys.stderr)
        return 1

    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
        print(f"wrote {args.json_out}")
    else:
        print(text)
    print(f"SUMMARY: {'PASS' if verdict == 'pass' else 'FAIL'} verdict={verdict}")
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-051a：金标整本执行入口。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.gold.plan051_run import (  # noqa: E402
    Plan051Blocked,
    run_selected,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="PLAN-051a gold full-retranslate runner")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore cache")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--entry", type=str, default=None)
    ap.add_argument("--include-synthetic", action="store_true")
    ap.add_argument("--out-root", type=Path, default=None)
    ap.add_argument("--gold-root", type=Path, default=None)
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    try:
        results = run_selected(
            include_synthetic=True if args.include_synthetic else None,
            entry_id=args.entry,
            limit=args.limit,
            out_root=args.out_root,
            gold_root_path=args.gold_root,
            force=args.force,
            dry_run=args.dry_run,
        )
    except Plan051Blocked as exc:
        print(f"SUMMARY: BLOCKED — {exc}", file=sys.stderr)
        return 2

    for row in results:
        print(json.dumps(row, ensure_ascii=False))
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json_out}")
    print(f"SUMMARY: PASS count={len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

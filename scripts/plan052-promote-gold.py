#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-052a：将 catalog 槽 promote 为 real。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.gold.plan052_promote import (  # noqa: E402
    Plan052PromoteError,
    product_ready,
    promote_entry,
    real_counts,
    resolve_source_file,
    source_row_for,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="PLAN-052 promote synthetic → real")
    ap.add_argument("--entry", required=True)
    ap.add_argument("--from", dest="from_path", type=Path, default=None)
    ap.add_argument("--from-inbox", action="store_true")
    ap.add_argument("--kind", default=None, help="override registry kind")
    ap.add_argument("--gold-root", type=Path, default=None)
    ap.add_argument("--catalog", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-assert", action="store_true")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    try:
        row = source_row_for(args.entry)
        from_inbox = args.from_inbox
        if args.from_path is None and not from_inbox:
            from_inbox = True
        src, kind, extra = resolve_source_file(
            entry_id=args.entry,
            from_path=args.from_path,
            from_inbox=from_inbox and args.from_path is None,
            root=args.gold_root,
        )
        if args.kind:
            kind = args.kind.strip()
        if args.from_path is not None and not kind:
            raise Plan052PromoteError("--kind required when kind cannot be resolved")
        result = promote_entry(
            args.entry,
            src=src,
            kind=kind,
            extra_tags=extra,
            gold_root_path=args.gold_root,
            catalog=args.catalog,
            dry_run=args.dry_run,
            skip_assert=args.skip_assert,
        )
    except Plan052PromoteError as exc:
        print(f"SUMMARY: BLOCKED — {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    counts = real_counts(args.catalog)
    print(f"real_counts={counts} product_ready={product_ready(counts)}")
    print("SUMMARY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

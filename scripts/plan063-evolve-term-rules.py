#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-063a：规则提案与人工 promote。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.persist.db import get_database_url, init_engine, reset_engine  # noqa: E402
from qyunslation.quality.evolve_rules import (  # noqa: E402
    current_rules_meta,
    promote,
    report,
    screen_pending,
    write_inbox,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Evolve term-candidate rules from decisions")
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--screen-pending", action="store_true")
    ap.add_argument("--promote", default=None, metavar="PROP-ID")
    args = ap.parse_args()
    if not (args.report or args.screen_pending or args.promote):
        print("FAIL: choose --report, --screen-pending, or --promote PROP", file=sys.stderr)
        return 1
    if args.promote:
        result = promote(args.promote)
        print(f"promoted={result['prop_id']} version={result['version']} fp={result['fingerprint']}")
        return 0
    url = args.database_url or get_database_url()
    if not url:
        print("FAIL: set QYUNSLATION_DATABASE_URL or --database-url", file=sys.stderr)
        return 1
    if args.dry_run or args.report:
        os.environ["QYUNSLATION_TERM_SCREEN"] = "0"
    reset_engine()
    init_engine(url)
    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    session = SessionLocal()
    try:
        proposals = screen_pending(session) if args.screen_pending else report(session)
        print(f"proposals={len(proposals)} {current_rules_meta()}")
        for item in proposals:
            print(f"  {item.get('type')} {item.get('source')} {item.get('reason')}")
        if not args.dry_run:
            write_inbox(proposals, title="screen-pending" if args.screen_pending else "report")
        session.rollback()
    finally:
        session.close()
        reset_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

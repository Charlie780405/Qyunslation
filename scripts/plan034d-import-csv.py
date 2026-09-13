#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-034d：把 glossaries/*.csv curated 幂等导入 Concept 表。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.glossary.governance import load_curated_entries  # noqa: E402
from qyunslation.persist.concept_repo import count_by_status, upsert_curated_from_entry  # noqa: E402
from qyunslation.persist.db import get_database_url, init_engine, reset_engine  # noqa: E402
from qyunslation.persist.models import Base  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Import curated CSV into concept tables")
    ap.add_argument("--database-url", default=None, help="override QYUNSLATION_DATABASE_URL")
    ap.add_argument("--create-all", action="store_true", help="Base.metadata.create_all (dev/sqlite)")
    args = ap.parse_args()

    url = args.database_url or get_database_url()
    if not url:
        print("FAIL: set QYUNSLATION_DATABASE_URL or --database-url", file=sys.stderr)
        return 1

    reset_engine()
    engine = init_engine(url)
    if args.create_all:
        Base.metadata.create_all(engine)

    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    entries = load_curated_entries()
    session = SessionLocal()
    try:
        n = 0
        for entry in entries:
            upsert_curated_from_entry(session, entry)
            n += 1
        session.commit()
        curated = count_by_status(session, "curated")
        print(f"imported_rows={n} curated_concepts={curated}")
    finally:
        session.close()
        reset_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

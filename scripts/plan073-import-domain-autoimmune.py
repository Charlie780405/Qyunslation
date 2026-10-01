#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-075e：将 glossaries/domain-autoimmune.csv 以 curated 状态导入 Concept。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CSV = ROOT / "glossaries" / "domain-autoimmune.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not CSV.is_file():
        print(f"FAIL: missing {CSV}")
        return 1

    from qyunslation.glossary.governance import load_glossary_csv
    from qyunslation.persist.concept_repo import count_by_status, upsert_curated_from_entry
    from qyunslation.persist.db import SessionLocal, get_database_url, init_engine, reset_engine

    url = get_database_url()
    if not url:
        print("FAIL: QYUNSLATION_DATABASE_URL not set")
        return 1
    reset_engine()
    init_engine(url)
    from qyunslation.persist.db import SessionLocal as SL

    if SL is None:
        print("FAIL: database session factory not initialized")
        return 1
    entries = load_glossary_csv(
        CSV, default_layer="domain-autoimmune", curated_only=True, skip_junk=True
    )
    if args.dry_run:
        print(f"dry-run rows={len(entries)}")
        return 0
    with SL() as session:
        for entry in entries:
            upsert_curated_from_entry(session, entry)
        session.commit()
        curated = count_by_status(session, "curated")
    print(f"imported_rows={len(entries)} curated_concepts={curated}")
    reset_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

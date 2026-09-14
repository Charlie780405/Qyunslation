#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-055：对已批准且无 embedding 的 tm_unit 批量补向量（LIVE）。"""
from __future__ import annotations

import argparse
import os
import sys

BATCH = 32


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill tm_unit_embedding")
    parser.add_argument("--limit", type=int, default=200, help="max units to embed")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    url = (os.environ.get("QYUNSLATION_DATABASE_URL") or "").strip()
    if not url:
        print("QYUNSLATION_DATABASE_URL required", file=sys.stderr)
        return 2

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from qyunslation.persist.db import init_engine, reset_engine
    from qyunslation.persist.models import TmUnit, TmUnitEmbedding
    from qyunslation.persist.tm_repo import upsert_unit_embedding

    reset_engine()
    engine = init_engine(url)
    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    session: Session = SessionLocal()
    try:
        embedded_ids = set(session.scalars(select(TmUnitEmbedding.unit_id)).all())
        stmt = (
            select(TmUnit)
            .where(TmUnit.approved.is_(True))
            .order_by(TmUnit.updated_at.desc())
            .limit(max(args.limit * 4, args.limit))
        )
        units = [u for u in session.scalars(stmt).all() if u.id not in embedded_ids]
        units = units[: args.limit]
        print(f"candidates={len(units)} dry_run={args.dry_run}")
        if args.dry_run or not units:
            return 0
        ok = 0
        for i in range(0, len(units), BATCH):
            chunk = units[i : i + BATCH]
            for unit in chunk:
                if upsert_unit_embedding(session, unit) is not None:
                    ok += 1
            session.commit()
        print(f"embedded={ok}")
        return 0
    finally:
        session.close()
        reset_engine()


if __name__ == "__main__":
    raise SystemExit(main())

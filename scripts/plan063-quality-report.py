#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-063b：领域准确度趋势报告。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.persist.db import get_database_url, init_engine, reset_engine  # noqa: E402
from qyunslation.persist.models import Tenant  # noqa: E402
from qyunslation.quality.ledger import domain_metrics  # noqa: E402
from sqlalchemy import select  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Quality ledger trend report")
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--tenant", default=None)
    ap.add_argument("--assert-no-regression", action="store_true")
    args = ap.parse_args()
    url = args.database_url or get_database_url()
    if not url:
        print("FAIL: set QYUNSLATION_DATABASE_URL or --database-url", file=sys.stderr)
        return 1
    reset_engine()
    init_engine(url)
    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    session = SessionLocal()
    try:
        tenant_id = args.tenant
        if not tenant_id:
            tenant = session.scalar(select(Tenant).limit(1))
            tenant_id = tenant.id if tenant else ""
        metrics = (
            domain_metrics(session, tenant_id=tenant_id)
            if tenant_id
            else {"runs": 0, "acceptance_rate": 0.0, "screen_blind_runs": 0}
        )
        print(
            f"runs={metrics.get('runs')} acceptance={metrics.get('acceptance_rate'):.3f} "
            f"screen_blind_runs={metrics.get('screen_blind_runs')}"
        )
        if args.assert_no_regression and int(metrics.get("screen_blind_runs") or 0) > 0:
            print(
                "REGRESSION: SCREEN_BLIND present; run "
                "QYUNSLATION_PLAN051_LIVE=1 bash scripts/verify-plan-051.sh",
                file=sys.stderr,
            )
            return 1
    finally:
        session.close()
        reset_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

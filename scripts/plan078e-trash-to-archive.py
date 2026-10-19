#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-078e：回滚前把回收站里的任务改为“已归档”，避免旧版本的列表里突然出现已删除的任务。

默认只演练（dry-run），打印会改动的任务；加 --apply 才写入。
正在被清除（purge_status 非空）的任务不处理——它们的文件可能已部分删除。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Turn recycle-bin tasks into archived tasks (rollback helper)")
    parser.add_argument("--apply", action="store_true", help="write the change (default: dry-run)")
    args = parser.parse_args()

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from qyunslation.persist.db import get_database_url, init_engine
    from qyunslation.persist.models import TranslationRunRecord

    url = get_database_url()
    if not url:
        print("FAIL: QYUNSLATION_DATABASE_URL required", file=sys.stderr)
        return 1
    engine = init_engine(url)

    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(TranslationRunRecord)
                .where(TranslationRunRecord.deleted_at.is_not(None))
                .order_by(TranslationRunRecord.tenant_id, TranslationRunRecord.created_at)
            )
        )
        movable = [row for row in rows if not row.purge_status]
        blocked = [row for row in rows if row.purge_status]
        for row in movable:
            print(f"{'ARCHIVE' if args.apply else 'would archive'} {row.tenant_id}/{row.id} (deleted {row.deleted_at:%Y-%m-%d})")
        for row in blocked:
            print(f"skip {row.tenant_id}/{row.id}: purge_status={row.purge_status}", file=sys.stderr)
        if args.apply:
            for row in movable:
                row.archived_at = row.archived_at or row.deleted_at
                row.archived_by = row.archived_by or row.deleted_by
                row.deleted_at = None
                row.deleted_by = None
                row.purge_after = None
            session.commit()
        print(
            f"{'changed' if args.apply else 'dry-run:'} {len(movable)} task(s); "
            f"{len(blocked)} skipped (purge in progress or failed)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

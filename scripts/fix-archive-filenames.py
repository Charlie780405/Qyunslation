#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-032 T3：修正归档索引中带流水线标记的 original_filename。

默认 dry-run，只打印将要变更的记录。确认后加 --apply 执行，执行前会自行备份 index.db。
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qyunslation.archive.filenames import original_filename_from_product  # noqa: E402

DEFAULT_DB = Path("/home/dev/pdf2zh/archive/index.db")


def plan_changes(db_path: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT archive_id, original_filename FROM archives ORDER BY rowid"
        ).fetchall()
    changes = []
    for row in rows:
        current = row["original_filename"]
        fixed = original_filename_from_product(current)
        if fixed != current:
            changes.append((row["archive_id"], current, fixed))
    return changes


def apply_changes(db_path: Path, changes: list[tuple[str, str, str]]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = db_path.with_suffix(f".bak-{stamp}.db")
    shutil.copy2(db_path, backup)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "UPDATE archives SET original_filename = ? WHERE archive_id = ?",
            [(fixed, aid) for aid, _cur, fixed in changes],
        )
        conn.commit()
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true", help="真正写入（默认只打印）")
    args = parser.parse_args()

    if not args.db.is_file():
        print(f"index.db 不存在: {args.db}")
        return 1

    changes = plan_changes(args.db)
    if not changes:
        print("无需修正。")
        return 0

    print(f"{len(changes)} 条记录将被修正：")
    for archive_id, current, fixed in changes:
        print(f"  {archive_id}\n    - {current}\n    + {fixed}")

    if not args.apply:
        print("\n以上为 dry-run。确认无误后加 --apply 执行。")
        return 0

    backup = apply_changes(args.db, changes)
    print(f"\n已修正 {len(changes)} 条；备份：{backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

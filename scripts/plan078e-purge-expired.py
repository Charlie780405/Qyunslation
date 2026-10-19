#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-078e：回收站到期任务的清除报告（默认只报告）与手动执行。

自动清除在首个发布周期内不启用：这个脚本默认只列出“已过保留期”和“上次清除没做完”的任务；
确认无误后加 --execute 才会真正删除文件和数据库记录（先提交标记，再删文件，最后删行）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Report (and optionally purge) expired recycle-bin tasks")
    parser.add_argument("--execute", action="store_true", help="purge them (default: report only)")
    args = parser.parse_args()

    from sqlalchemy.orm import Session

    from qyunslation.api.v1 import purge_expired_runs
    from qyunslation.persist.db import get_database_url, init_engine

    url = get_database_url()
    if not url:
        print("FAIL: QYUNSLATION_DATABASE_URL required", file=sys.stderr)
        return 1
    engine = init_engine(url)
    with Session(engine) as session:
        report = purge_expired_runs(session, execute=args.execute, actor_sub="system:plan078e-purge-expired")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

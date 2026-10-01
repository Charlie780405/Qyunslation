#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-072e：清理无 DB 记录的 preflight / translation-run 磁盘目录。"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _roots() -> tuple[Path, Path]:
    preflight = Path(os.environ.get("QYUNSLATION_PREFLIGHT_ROOT") or "var/preflights")
    runs = Path(os.environ.get("QYUNSLATION_RUNNER_ROOT") or "var/translation-runs")
    if not preflight.is_absolute():
        preflight = ROOT / preflight
    if not runs.is_absolute():
        runs = ROOT / runs
    return preflight, runs


def main() -> int:
    parser = argparse.ArgumentParser(description="GC orphan preflight/run directories")
    parser.add_argument("--apply", action="store_true", help="delete orphan directories")
    args = parser.parse_args()

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from qyunslation.persist.db import get_database_url, init_engine
    from qyunslation.persist.models import PreflightRecord, TranslationRunRecord

    url = get_database_url()
    if not url:
        print("FAIL: QYUNSLATION_DATABASE_URL required", file=sys.stderr)
        return 1
    init_engine(url)
    engine = init_engine(url)
    preflight_root, run_root = _roots()
    orphans: list[Path] = []

    with Session(engine) as session:
        known_preflights = {
            row.storage_key.split("/", 1)[-1]
            for row in session.scalars(select(PreflightRecord))
        }
        known_runs = {row.id for row in session.scalars(select(TranslationRunRecord))}

    if preflight_root.is_dir():
        for tenant_dir in preflight_root.iterdir():
            if not tenant_dir.is_dir():
                continue
            for path in tenant_dir.iterdir():
                if path.name.startswith(".") or not path.is_file():
                    continue
                if path.name not in known_preflights and path.name.endswith(
                    tuple({".pdf", ".docx", ".pptx", ".txt", ".md", ".png", ".jpg", ".jpeg"})
                ):
                    orphans.append(path)

    if run_root.is_dir():
        for tenant_dir in run_root.iterdir():
            if not tenant_dir.is_dir():
                continue
            for run_dir in tenant_dir.iterdir():
                if run_dir.is_dir() and run_dir.name not in known_runs:
                    orphans.append(run_dir)

    print(f"orphans={len(orphans)} apply={args.apply}")
    for path in orphans:
        print(path)
        if args.apply:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

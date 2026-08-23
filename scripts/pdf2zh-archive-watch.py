#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""监听 pdf2zh 输出目录，稳定后上传 MinIO 并写 SQLite 索引。"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qyunslation.archive.pdf2zh_ingest import (  # noqa: E402
    build_pdf2zh_archive_backend,
    ingest_pdf2zh_group,
    output_group_key,
)

logger = logging.getLogger("pdf2zh-archive-watch")


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def cfg_from_env() -> dict:
    return {
        "watch_dir": os.environ.get("PDF2ZH_ARCHIVE_WATCH_DIR", "/home/dev/pdf2zh/out"),
        "state_db": os.environ.get(
            "PDF2ZH_ARCHIVE_STATE_DB", "/home/dev/pdf2zh/.archive-state.db"
        ),
        "index_db": os.environ.get(
            "PDF2ZH_ARCHIVE_INDEX_DB", "/home/dev/pdf2zh/archive/index.db"
        ),
        "local_root": os.environ.get(
            "PDF2ZH_ARCHIVE_LOCAL_ROOT", "/home/dev/pdf2zh/archive"
        ),
        "storage_backend": os.environ.get("PDF2ZH_ARCHIVE_STORAGE", "minio"),
        "minio_endpoint": os.environ.get("PDF2ZH_MINIO_ENDPOINT", "127.0.0.1:9002"),
        "minio_access_key": os.environ.get("PDF2ZH_MINIO_ACCESS_KEY", ""),
        "minio_secret_key": os.environ.get("PDF2ZH_MINIO_SECRET_KEY", ""),
        "minio_bucket": os.environ.get("PDF2ZH_MINIO_BUCKET", "translate-docs"),
        "minio_secure": os.environ.get("PDF2ZH_MINIO_SECURE", "false").lower()
        in ("1", "true", "yes"),
        "minio_prefix": os.environ.get("PDF2ZH_MINIO_PREFIX", "pdf2zh"),
        "poll_seconds": float(os.environ.get("PDF2ZH_ARCHIVE_POLL_SECONDS", "5")),
        "settle_seconds": float(os.environ.get("PDF2ZH_ARCHIVE_SETTLE_SECONDS", "8")),
    }


class GroupStateDB:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingested_groups (
                    group_key TEXT PRIMARY KEY,
                    archive_id TEXT NOT NULL,
                    ingested_at TEXT NOT NULL
                )
                """
            )

    def is_done(self, group_key: str) -> bool:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT 1 FROM ingested_groups WHERE group_key = ?", (group_key,)
            ).fetchone()
        return row is not None

    def mark_done(self, group_key: str, archive_id: str) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ingested_groups (group_key, archive_id, ingested_at) VALUES (?, ?, ?)",
                (group_key, archive_id, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            )
            conn.commit()


def scan_groups(watch_dir: Path) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    if not watch_dir.is_dir():
        return groups
    for path in watch_dir.iterdir():
        if not path.is_file():
            continue
        key = output_group_key(path.name)
        if key:
            groups[key].append(path)
    return groups


def files_stable(paths: list[Path], settle_seconds: float) -> bool:
    now = time.time()
    for path in paths:
        try:
            st = path.stat()
        except OSError:
            return False
        if now - st.st_mtime < settle_seconds:
            return False
        if st.st_size <= 0:
            return False
    return any(p.name.lower().endswith(".pdf") for p in paths)


def run_once(cfg: dict, *, dry_run: bool = False) -> int:
    watch_dir = Path(cfg["watch_dir"])
    state = GroupStateDB(Path(cfg["state_db"]))
    storage, index = build_pdf2zh_archive_backend(cfg)
    ingested = 0

    for group_key, paths in scan_groups(watch_dir).items():
        if state.is_done(group_key):
            continue
        if not files_stable(paths, cfg["settle_seconds"]):
            continue
        if dry_run:
            logger.info("dry-run 将归档 %s (%d 文件)", group_key, len(paths))
            ingested += 1
            continue
        record = ingest_pdf2zh_group(
            storage=storage,
            index=index,
            group_key=group_key,
            paths=paths,
        )
        state.mark_done(group_key, record.archive_id)
        logger.info("已归档 %s → %s (%d 文件)", group_key, record.archive_id, len(paths))
        ingested += 1
    return ingested


def main() -> int:
    parser = argparse.ArgumentParser(description="pdf2zh 输出 MinIO 旁路归档")
    parser.add_argument(
        "--env-file",
        default="/home/dev/pdf2zh/archive.env",
        help="环境变量文件路径",
    )
    parser.add_argument("--once", action="store_true", help="扫描一次后退出")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不上传")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    load_env_file(Path(args.env_file))
    cfg = cfg_from_env()

    if cfg["storage_backend"] == "minio" and not cfg["minio_access_key"]:
        logger.error("缺少 PDF2ZH_MINIO_ACCESS_KEY（见 archive.env.example）")
        return 1

    logger.info("监听 %s backend=%s bucket=%s", cfg["watch_dir"], cfg["storage_backend"], cfg["minio_bucket"])

    if args.once:
        n = run_once(cfg, dry_run=args.dry_run)
        logger.info("完成，处理 %d 组", n)
        return 0

    while True:
        try:
            run_once(cfg, dry_run=args.dry_run)
        except Exception:
            logger.exception("归档轮询失败")
        time.sleep(cfg["poll_seconds"])


if __name__ == "__main__":
    raise SystemExit(main())

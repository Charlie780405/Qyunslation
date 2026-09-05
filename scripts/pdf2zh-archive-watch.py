#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""监听 pdf2zh 输出目录，稳定后上传 MinIO 并写 SQLite 索引。"""
from __future__ import annotations

import argparse
import fcntl
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
from qyunslation.archive.pdf2zh_vault import ingest_vault_and_index  # noqa: E402

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
        "session_dir": os.environ.get(
            "PDF2ZH_ARCHIVE_SESSION_DIR", "/home/dev/pdf2zh/pdf2zh_files"
        ),
        "state_db": os.environ.get(
            "PDF2ZH_ARCHIVE_STATE_DB", "/home/dev/pdf2zh/archive/watch-state.db"
        ),
        "lock_file": os.environ.get(
            "PDF2ZH_ARCHIVE_LOCK_FILE", "/home/dev/pdf2zh/archive/watch.lock"
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
        "vault_enable": os.environ.get("PDF2ZH_VAULT_ENABLE", "true").lower()
        in ("1", "true", "yes"),
        "vault_root": os.environ.get(
            "PDF2ZH_VAULT_ROOT", "/home/dev/Targets/vault"
        ),
        "vault_translations_dir": os.environ.get(
            "PDF2ZH_VAULT_TRANSLATIONS_DIR", "10-Source-Documents/Translations"
        ),
        "vector_index_enable": os.environ.get(
            "PDF2ZH_VECTOR_INDEX_ENABLE", "true"
        ).lower()
        in ("1", "true", "yes"),
        "hermes_root": os.environ.get("HERMES_ROOT", "/home/dev/Hermes"),
        "hermes_python": os.environ.get(
            "HERMES_PYTHON",
            str(Path.home() / ".hermes/hermes-agent/venv/bin/python3"),
        ),
    }


class GroupStateDB:
    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 长连接：sqlite3 的 with 只提交事务不 close，轮询会泄漏 fd
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ingested_groups (
                group_key TEXT PRIMARY KEY,
                archive_id TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                vault_note_path TEXT
            )
            """
        )
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(ingested_groups)").fetchall()
        }
        if "vault_note_path" not in cols:
            self._conn.execute(
                "ALTER TABLE ingested_groups ADD COLUMN vault_note_path TEXT"
            )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def is_done(self, group_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM ingested_groups WHERE group_key = ?", (group_key,)
        ).fetchone()
        return row is not None

    def get(self, group_key: str) -> tuple[str, str | None] | None:
        row = self._conn.execute(
            "SELECT archive_id, vault_note_path FROM ingested_groups WHERE group_key = ?",
            (group_key,),
        ).fetchone()
        if not row:
            return None
        return row[0], row[1]

    def mark_done(
        self, group_key: str, archive_id: str, vault_note_path: str | None = None
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO ingested_groups
            (group_key, archive_id, ingested_at, vault_note_path)
            VALUES (?, ?, ?, ?)
            """,
            (
                group_key,
                archive_id,
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                vault_note_path,
            ),
        )
        self._conn.commit()


def _collect_output_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in root.iterdir():
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in path.iterdir() if p.is_file())
    return files


def scan_groups(*watch_dirs: Path) -> dict[str, list[Path]]:
    from qyunslation.archive.pdf2zh_ingest import find_source_pdf

    groups: dict[str, list[Path]] = defaultdict(list)
    for watch_dir in watch_dirs:
        for path in _collect_output_files(watch_dir):
            key = output_group_key(path.name)
            if key:
                groups[key].append(path)
    # 同名文件跨 session 去重，保留最新 mtime
    for key, paths in list(groups.items()):
        best: dict[str, Path] = {}
        for p in paths:
            prev = best.get(p.name)
            if prev is None or p.stat().st_mtime >= prev.stat().st_mtime:
                best[p.name] = p
        paths = list(best.values())
        src = find_source_pdf(key, paths)
        if src is not None and src.name not in best:
            paths.append(src)
        groups[key] = paths
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
    # 至少有一份译稿（PDF/md/docx），不能仅凭原文 PDF 触发入库
    return any(
        p.name.lower().endswith(
            (".mono.pdf", ".dual.pdf", ".letter-mono.pdf", ".zh.md", ".zh.docx")
        )
        for p in paths
    )


def run_once(cfg: dict, *, dry_run: bool = False) -> int:
    lock_path = Path(cfg.get("lock_file") or cfg["state_db"]).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lockf:
        try:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.debug("归档锁占用，跳过本轮")
            return 0

        watch_dir = Path(cfg["watch_dir"])
        session_dir = Path(cfg.get("session_dir") or "")
        state = GroupStateDB(Path(cfg["state_db"]))
        storage, index = build_pdf2zh_archive_backend(cfg)
        ingested = 0

        for group_key, paths in scan_groups(watch_dir, session_dir).items():
            if not files_stable(paths, cfg["settle_seconds"]):
                continue

            existing = state.get(group_key)
            if existing and existing[1]:
                continue
            if existing and not cfg.get("vault_enable"):
                continue

            if dry_run:
                logger.info("dry-run 将归档 %s (%d 文件)", group_key, len(paths))
                ingested += 1
                continue

            if existing:
                record = index.get(existing[0])
                if not record:
                    logger.warning("索引无记录 %s，跳过", existing[0])
                    continue
            else:
                record = ingest_pdf2zh_group(
                    storage=storage,
                    index=index,
                    group_key=group_key,
                    paths=paths,
                )

            vault_rel = None
            if cfg.get("vault_enable"):
                vault_rel = ingest_vault_and_index(
                    record=record,
                    group_key=group_key,
                    output_paths=paths,
                    vault_root=Path(cfg["vault_root"]),
                    hermes_root=Path(cfg["hermes_root"]),
                    hermes_python=Path(cfg["hermes_python"]),
                    translations_dir=cfg.get(
                        "vault_translations_dir", "10-Source-Documents/Translations"
                    ),
                    index_enable=bool(cfg.get("vector_index_enable")),
                )

            state.mark_done(group_key, record.archive_id, vault_rel)
            logger.info(
                "已归档 %s → %s vault=%s (%d 文件)",
                group_key,
                record.archive_id,
                vault_rel or "-",
                len(paths),
            )
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

    logger.info(
        "监听 %s session=%s backend=%s bucket=%s",
        cfg["watch_dir"],
        cfg.get("session_dir"),
        cfg["storage_backend"],
        cfg["minio_bucket"],
    )

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

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""监听 office_out，稳定后写入与 pdf2zh 同一 archive index / MinIO / Vault。"""
from __future__ import annotations

import argparse
import fcntl
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qyunslation.archive.index_db import ArchiveIndex  # noqa: E402
from qyunslation.archive.models import ArchiveFileRef, ArchiveRecord  # noqa: E402
from qyunslation.archive.pdf2zh_ingest import build_pdf2zh_archive_backend  # noqa: E402
from qyunslation.archive.pdf2zh_vault import ingest_vault_and_index  # noqa: E402

logger = logging.getLogger("office-archive-watch")


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def cfg_from_env() -> dict:
    return {
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
        "vault_root": os.environ.get("PDF2ZH_VAULT_ROOT", "/home/dev/Targets/vault"),
        "vault_translations_dir": os.environ.get(
            "PDF2ZH_VAULT_TRANSLATIONS_DIR", "10-Source-Documents/Translations"
        ),
        "vector_index_enable": os.environ.get("PDF2ZH_VECTOR_INDEX_ENABLE", "true").lower()
        in ("1", "true", "yes"),
        "hermes_root": os.environ.get("HERMES_ROOT", "/home/dev/Hermes"),
        "hermes_python": os.environ.get(
            "HERMES_PYTHON",
            str(Path.home() / ".hermes/hermes-agent/venv/bin/python3"),
        ),
    }


def is_office_product(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.endswith(".zh.docx")
        or name.endswith("_translated.docx")
        or name.endswith(".zh.png")
        or name.endswith(".zh.jpg")
        or name.endswith(".zh.jpeg")
        or name.endswith(".zh.webp")
    )


def ingest_one(path: Path, storage, index: ArchiveIndex, cfg: dict) -> str:
    archive_id = index.allocate_id()
    created_at = ArchiveIndex.now_iso()
    key = f"{archive_id}/translated/{path.name}"
    storage.put_file(key, path)
    ft = "docx" if path.suffix.lower() == ".docx" else "image"
    file_refs = [
        ArchiveFileRef(
            role="translated",
            file_type=ft,
            filename=path.name,
            storage_key=key,
            size_bytes=path.stat().st_size,
        )
    ]
    record = ArchiveRecord(
        archive_id=archive_id,
        task_id=f"office-{path.stem}",
        original_filename=path.name,
        to_lang="zh",
        workflow_type="office",
        created_at=created_at,
        storage_backend=storage.name,
        files=file_refs,
        extra={"source": "office_out"},
    )
    index.insert(record)
    try:
        ingest_vault_and_index(
            record=record,
            group_key=path.stem,
            output_paths=[path],
            vault_root=Path(cfg["vault_root"]),
            hermes_root=Path(cfg["hermes_root"]),
            hermes_python=Path(cfg["hermes_python"]),
            translations_dir=cfg["vault_translations_dir"],
            index_enable=bool(cfg.get("vector_index_enable")),
        )
    except Exception as exc:
        logger.warning("vault/index failed for %s: %s", archive_id, exc)
    logger.info("archived %s as %s", path.name, archive_id)
    return archive_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="/home/dev/pdf2zh/office.env")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    load_env_file(Path("/home/dev/pdf2zh/archive.env"))
    load_env_file(Path(args.env))

    watch = Path(os.environ.get("QYUNSLATION_OFFICE_OUT", "/home/dev/pdf2zh/office_out"))
    watch.mkdir(parents=True, exist_ok=True)
    lock_path = Path(
        os.environ.get("OFFICE_ARCHIVE_LOCK", "/home/dev/pdf2zh/archive/office-watch.lock")
    )
    state_db = Path(
        os.environ.get(
            "OFFICE_ARCHIVE_STATE_DB", "/home/dev/pdf2zh/archive/office-watch-state.db"
        )
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = cfg_from_env()
    storage, index = build_pdf2zh_archive_backend(cfg)

    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        conn = sqlite3.connect(state_db)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS done (path TEXT PRIMARY KEY, archive_id TEXT, ts REAL)"
        )
        conn.commit()

        def scan_once() -> None:
            for p in sorted(watch.iterdir()):
                if not p.is_file() or not is_office_product(p):
                    continue
                if conn.execute("SELECT 1 FROM done WHERE path=?", (str(p),)).fetchone():
                    continue
                if time.time() - p.stat().st_mtime < 3:
                    continue
                try:
                    aid = ingest_one(p, storage, index, cfg)
                    conn.execute(
                        "INSERT OR REPLACE INTO done(path, archive_id, ts) VALUES (?,?,?)",
                        (str(p), aid, time.time()),
                    )
                    conn.commit()
                except Exception as exc:
                    logger.exception("ingest failed %s: %s", p, exc)

        if args.once:
            scan_once()
            return 0
        while True:
            scan_once()
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())

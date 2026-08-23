# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qyunslation.archive.models import ArchiveFileRef, ArchiveRecord


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ArchiveIndex:
    """SQLite 元数据索引与 DT-YYYY-NNNN 编号生成。"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS archive_counter (
                    year INTEGER PRIMARY KEY,
                    next_seq INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS archives (
                    archive_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    to_lang TEXT NOT NULL,
                    workflow_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    storage_backend TEXT NOT NULL,
                    vault_note_path TEXT,
                    source_text_preview TEXT,
                    translated_text_preview TEXT,
                    extra_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS archive_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    archive_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    storage_key TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (archive_id) REFERENCES archives(archive_id)
                );
                CREATE INDEX IF NOT EXISTS idx_archives_created ON archives(created_at DESC);
                """
            )

    def allocate_id(self) -> str:
        year = datetime.now(timezone.utc).year
        with self._connect() as conn:
            row = conn.execute(
                "SELECT next_seq FROM archive_counter WHERE year = ?", (year,)
            ).fetchone()
            if row is None:
                seq = 1
                conn.execute(
                    "INSERT INTO archive_counter (year, next_seq) VALUES (?, ?)",
                    (year, 2),
                )
            else:
                seq = int(row["next_seq"])
                conn.execute(
                    "UPDATE archive_counter SET next_seq = ? WHERE year = ?",
                    (seq + 1, year),
                )
            conn.commit()
        return f"DT-{year}-{seq:04d}"

    def insert(self, record: ArchiveRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO archives (
                    archive_id, task_id, original_filename, to_lang, workflow_type,
                    created_at, storage_backend, vault_note_path,
                    source_text_preview, translated_text_preview, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.archive_id,
                    record.task_id,
                    record.original_filename,
                    record.to_lang,
                    record.workflow_type,
                    record.created_at,
                    record.storage_backend,
                    record.vault_note_path,
                    record.source_text_preview,
                    record.translated_text_preview,
                    json.dumps(record.extra, ensure_ascii=False),
                ),
            )
            for f in record.files:
                conn.execute(
                    """
                    INSERT INTO archive_files
                    (archive_id, role, file_type, filename, storage_key, size_bytes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.archive_id,
                        f.role,
                        f.file_type,
                        f.filename,
                        f.storage_key,
                        f.size_bytes,
                    ),
                )
            conn.commit()

    def get(self, archive_id: str) -> ArchiveRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM archives WHERE archive_id = ?", (archive_id,)
            ).fetchone()
            if row is None:
                return None
            files = conn.execute(
                "SELECT * FROM archive_files WHERE archive_id = ? ORDER BY id",
                (archive_id,),
            ).fetchall()
        return self._row_to_record(row, files)

    def list_records(
        self, *, limit: int = 50, offset: int = 0, prefix: str = ""
    ) -> tuple[list[ArchiveRecord], int]:
        where = ""
        params: list[Any] = []
        if prefix:
            where = "WHERE archive_id LIKE ? OR original_filename LIKE ?"
            like = f"%{prefix}%"
            params.extend([like, like])

        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM archives {where}", params
            ).fetchone()["c"]
            rows = conn.execute(
                f"""
                SELECT * FROM archives {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
            result: list[ArchiveRecord] = []
            for row in rows:
                files = conn.execute(
                    "SELECT * FROM archive_files WHERE archive_id = ? ORDER BY id",
                    (row["archive_id"],),
                ).fetchall()
                result.append(self._row_to_record(row, files))
        return result, int(total)

    def _row_to_record(self, row: sqlite3.Row, files: list[sqlite3.Row]) -> ArchiveRecord:
        extra = json.loads(row["extra_json"] or "{}")
        return ArchiveRecord(
            archive_id=row["archive_id"],
            task_id=row["task_id"],
            original_filename=row["original_filename"],
            to_lang=row["to_lang"],
            workflow_type=row["workflow_type"],
            created_at=row["created_at"],
            storage_backend=row["storage_backend"],
            vault_note_path=row["vault_note_path"],
            source_text_preview=row["source_text_preview"] or "",
            translated_text_preview=row["translated_text_preview"] or "",
            files=[
                ArchiveFileRef(
                    role=f["role"],
                    file_type=f["file_type"],
                    filename=f["filename"],
                    storage_key=f["storage_key"],
                    size_bytes=int(f["size_bytes"]),
                )
                for f in files
            ],
            extra=extra,
        )

    @staticmethod
    def now_iso() -> str:
        return _utc_now_iso()

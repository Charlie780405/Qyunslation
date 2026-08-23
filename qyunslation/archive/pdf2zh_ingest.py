# SPDX-License-Identifier: MPL-2.0
"""pdf2zh 输出目录旁路归档（MinIO + SQLite 索引，不接 Vault）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from qyunslation.archive.index_db import ArchiveIndex
from qyunslation.archive.models import ArchiveFileRef, ArchiveRecord
from qyunslation.archive.storage import StorageBackend, build_storage_backend

_OUTPUT_SUFFIX_RE = re.compile(r"\.(mono|dual|glossary)\.(pdf|csv)$", re.I)


def output_group_key(filename: str) -> str | None:
    if not _OUTPUT_SUFFIX_RE.search(filename):
        return None
    return _OUTPUT_SUFFIX_RE.sub("", filename)


def infer_original_filename(group_key: str) -> str:
    stem = group_key.split(".no_watermark.")[0]
    return f"{stem}.pdf"


def infer_to_lang(group_key: str) -> str:
    parts = group_key.split(".")
    if "no_watermark" in parts:
        idx = parts.index("no_watermark")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "zh"


def classify_output_file(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".mono.pdf"):
        return "mono_pdf"
    if name.endswith(".dual.pdf"):
        return "dual_pdf"
    if name.endswith(".glossary.csv"):
        return "glossary_csv"
    return "other"


def ingest_pdf2zh_group(
    *,
    storage: StorageBackend,
    index: ArchiveIndex,
    group_key: str,
    paths: list[Path],
    to_lang: str | None = None,
    task_id: str = "",
) -> ArchiveRecord:
    archive_id = index.allocate_id()
    created_at = ArchiveIndex.now_iso()
    file_refs: list[ArchiveFileRef] = []
    original_filename = infer_original_filename(group_key)
    lang = to_lang or infer_to_lang(group_key)

    for path in sorted(paths):
        ft = classify_output_file(path)
        key = f"{archive_id}/translated/{path.name}"
        storage.put_file(key, path)
        file_refs.append(
            ArchiveFileRef(
                role="translated",
                file_type=ft,
                filename=path.name,
                storage_key=key,
                size_bytes=path.stat().st_size,
            )
        )

    record = ArchiveRecord(
        archive_id=archive_id,
        task_id=task_id or f"pdf2zh-{group_key}",
        original_filename=original_filename,
        to_lang=lang,
        workflow_type="pdf2zh",
        created_at=created_at,
        storage_backend=storage.name,
        files=file_refs,
        extra={"output_group": group_key},
    )
    index.insert(record)
    return record


def build_pdf2zh_archive_backend(cfg: dict[str, Any]) -> tuple[StorageBackend, ArchiveIndex]:
    local_root = Path(cfg["local_root"])
    local_root.mkdir(parents=True, exist_ok=True)
    storage = build_storage_backend(
        cfg["storage_backend"],
        local_root / "objects",
        minio_endpoint=cfg.get("minio_endpoint", ""),
        minio_access_key=cfg.get("minio_access_key", ""),
        minio_secret_key=cfg.get("minio_secret_key", ""),
        minio_bucket=cfg.get("minio_bucket", "translate-docs"),
        minio_secure=bool(cfg.get("minio_secure", False)),
        minio_prefix=cfg.get("minio_prefix", "pdf2zh"),
    )
    index = ArchiveIndex(Path(cfg["index_db"]))
    return storage, index

# SPDX-License-Identifier: MPL-2.0
"""pdf2zh 输出目录旁路归档（MinIO + SQLite 索引，不接 Vault）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from qyunslation.archive.index_db import ArchiveIndex
from qyunslation.archive.models import ArchiveFileRef, ArchiveRecord
from qyunslation.archive.storage import StorageBackend, build_storage_backend

# 更具体的后缀在前；捕获组为剥后缀后的 stem（仍可能含 .hpd-ocr / .no_watermark.xx）
_OUTPUT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(.+)\.letter-mono\.pdf$", re.I), "letter_mono_pdf"),
    (re.compile(r"^(.+)\.mono\.pdf$", re.I), "mono_pdf"),
    (re.compile(r"^(.+)\.dual\.pdf$", re.I), "dual_pdf"),
    (re.compile(r"^(.+)\.glossary\.csv$", re.I), "glossary_csv"),
    (re.compile(r"^(.+)\.zh\.md$", re.I), "translated_md"),
    (re.compile(r"^(.+)\.zh\.docx$", re.I), "translated_docx"),
]

_NO_WATERMARK_RE = re.compile(r"\.no_watermark(?:\.[^.]+)?", re.I)
_HPD_OCR_RE = re.compile(r"\.hpd-ocr", re.I)
_TRAIL_LANG_RE = re.compile(r"\.(zh-CN|zh|en)$", re.I)


def normalize_group_stem(stem: str) -> str:
    """剥掉 .hpd-ocr / .no_watermark.<lang> / 尾部语言码，使原文与各格式产物同组。"""
    s = stem
    s = _NO_WATERMARK_RE.sub("", s)
    s = _HPD_OCR_RE.sub("", s)
    s = _TRAIL_LANG_RE.sub("", s)
    return s


def output_group_key(filename: str) -> str | None:
    name = Path(filename).name
    for pat, _kind in _OUTPUT_PATTERNS:
        m = pat.match(name)
        if m:
            return normalize_group_stem(m.group(1))
    return None


def infer_original_filename(group_key: str) -> str:
    return f"{group_key}.pdf"


def infer_to_lang(group_key: str) -> str:
    # 分组键已规范化，默认 zh；具体语言在文件名里时由调用方覆盖
    return "zh"


def classify_output_file(path: Path, *, group_key: str | None = None) -> str:
    name = path.name
    for pat, kind in _OUTPUT_PATTERNS:
        if pat.match(name):
            return kind
    if group_key and name == f"{group_key}.pdf":
        return "source_pdf"
    return "other"


def find_source_pdf(group_key: str, paths: list[Path]) -> Path | None:
    target = f"{group_key}.pdf"
    dirs = {p.parent for p in paths}
    for d in dirs:
        candidate = d / target
        if candidate.is_file():
            return candidate
    return None


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

    # 附带原文（若在同目录）
    all_paths = list(paths)
    src = find_source_pdf(group_key, all_paths)
    if src is not None and src not in all_paths:
        all_paths.append(src)

    for path in sorted(all_paths, key=lambda p: p.name.lower()):
        ft = classify_output_file(path, group_key=group_key)
        if ft == "other":
            continue
        if ft == "source_pdf":
            role = "source"
            key = f"{archive_id}/source/{path.name}"
        else:
            role = "translated"
            key = f"{archive_id}/translated/{path.name}"
        storage.put_file(key, path)
        file_refs.append(
            ArchiveFileRef(
                role=role,
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

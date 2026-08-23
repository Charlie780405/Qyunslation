# SPDX-License-Identifier: MPL-2.0
"""翻译文件归档（本地 / MinIO + SQLite 索引）。"""

from qyunslation.archive.pdf2zh_ingest import (
    build_pdf2zh_archive_backend,
    ingest_pdf2zh_group,
    output_group_key,
)

__all__ = [
    "build_pdf2zh_archive_backend",
    "ingest_pdf2zh_group",
    "output_group_key",
]

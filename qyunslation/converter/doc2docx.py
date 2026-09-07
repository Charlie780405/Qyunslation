# SPDX-License-Identifier: MPL-2.0
"""PLAN-005b：.doc → .docx（LibreOffice headless）。"""
from __future__ import annotations

from pathlib import Path

from qyunslation.converter.office import LibreOfficeConverter
from qyunslation.structure.models import SourceFormat


def ensure_docx(filename: str, content: bytes) -> tuple[str, bytes]:
    """若为 .doc 则转 docx；已是 docx 原样返回。无 soffice 时抛清晰错误。"""
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return filename, content
    if suffix != ".doc":
        return filename, content

    result = LibreOfficeConverter().convert(filename, content, SourceFormat.DOC)
    return result.output_name, result.content

# SPDX-License-Identifier: MPL-2.0
"""从 PDF 提取纯文本（供 Vault 摘录与向量索引）。"""
from __future__ import annotations

from pathlib import Path


def extract_pdf_text(path: Path, *, max_chars: int = 120_000) -> str:
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("需要 pymupdf：python3 -m pip install pymupdf") from exc

    doc = pymupdf.open(str(path))
    try:
        parts: list[str] = []
        total = 0
        for page in doc:
            chunk = (page.get_text("text") or "").strip()
            if not chunk:
                continue
            parts.append(chunk)
            total += len(chunk)
            if total >= max_chars:
                break
        return "\n\n".join(parts)[:max_chars]
    finally:
        doc.close()


def pick_mono_pdf(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.name.lower().endswith(".mono.pdf"):
            return p
    for p in paths:
        if p.suffix.lower() == ".pdf":
            return p
    return None

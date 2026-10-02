"""Bounded text extraction for AD domain gating and non-PDF QA."""
from __future__ import annotations

from pathlib import Path


def extract_docx_text(content: bytes) -> str:
    try:
        from io import BytesIO

        from qyunslation.structure.docx_walk import walk_docx

        _, _, _, texts = walk_docx(content)
        return "\n".join(text for text in texts if text and text.strip())
    except Exception:
        return ""


def extract_preflight_text(path: Path) -> str:
    if not path.is_file():
        return ""
    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        try:
            from qyunslation.pipeline.qa.pdf_inspect import read_pdf_facts

            facts = read_pdf_facts(path)
            return facts.text if facts else ""
        except Exception:
            return ""
    if suffix == ".docx":
        try:
            return extract_docx_text(path.read_bytes())[:500_000]
        except OSError:
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:500_000]
    except OSError:
        return ""


def extract_translated_text(path: Path) -> str:
    return extract_preflight_text(path)

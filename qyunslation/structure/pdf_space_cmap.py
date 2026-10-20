# SPDX-License-Identifier: MPL-2.0
"""PLAN-082 S4: repair blank-glyph CIDs missing from ToUnicode CMaps.

BabelDOC / font subsetting sometimes emits a spacing glyph (CID 3) without a
ToUnicode entry. PyMuPDF then surfaces it as U+0003 when
``TEXT_USE_CID_FOR_UNKNOWN_UNICODE`` is set, which looks like garbled text in
copy/paste and QA even though the page renders as a blank/space.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_BEGIN_BFCHAR_RE = re.compile(r"(?m)^(\d+)\s+beginbfchar\s*$")


def fix_space_cmap_enabled() -> bool:
    raw = (os.environ.get("QYUNSLATION_FIX_SPACE_CMAP") or "1").strip().casefold()
    return raw not in {"0", "false", "off", "no"}


def _inject_space_mapping(stream: bytes) -> tuple[bytes, bool]:
    """Add ``<0003><0020>`` to the first ``beginbfchar`` block when CID 3 is missing."""
    if b"beginbfchar" not in stream:
        return stream, False
    text = stream.decode("latin-1", errors="surrogateescape")
    if re.search(r"<0003>\s*<", text):
        return stream, False
    match = _BEGIN_BFCHAR_RE.search(text)
    if not match:
        return stream, False
    count = int(match.group(1))
    insertion = f"{count + 1} beginbfchar\n<0003><0020>\n"
    start, end = match.span()
    updated = text[:start] + insertion + text[end:].lstrip("\n")
    return updated.encode("latin-1", errors="surrogateescape"), True


def fix_space_cmap_pdf(path: Path) -> dict[str, Any]:
    """Rewrite ToUnicode streams in ``path`` so CID 3 maps to U+0020.

    Returns a small summary; never raises to callers that must stay fail-open.
    """
    summary: dict[str, Any] = {"path": str(path), "streams_patched": 0, "enabled": fix_space_cmap_enabled()}
    if not fix_space_cmap_enabled() or not path.is_file():
        return summary
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except ImportError:
        try:
            import fitz  # type: ignore[import-not-found,no-redef]
        except ImportError:
            summary["error"] = "pymupdf_unavailable"
            return summary
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001
        summary["error"] = type(exc).__name__
        return summary
    try:
        patched = 0
        for xref in range(1, doc.xref_length()):
            try:
                stream = doc.xref_stream(xref)
            except Exception:
                continue
            if not stream:
                continue
            new_stream, changed = _inject_space_mapping(stream)
            if not changed:
                continue
            try:
                doc.update_stream(xref, new_stream)
                patched += 1
            except Exception:
                continue
        summary["streams_patched"] = patched
        if patched:
            tmp = path.with_suffix(path.suffix + ".spacemap.tmp")
            doc.save(str(tmp), garbage=3, deflate=True)
            tmp.replace(path)
        return summary
    except Exception as exc:  # noqa: BLE001
        summary["error"] = type(exc).__name__
        return summary
    finally:
        doc.close()


def fix_space_cmap_tree(output_dir: Path) -> dict[str, Any]:
    """Apply :func:`fix_space_cmap_pdf` to every PDF under ``output_dir``."""
    if not fix_space_cmap_enabled() or not output_dir.is_dir():
        return {"enabled": fix_space_cmap_enabled(), "files": {}}
    files: dict[str, Any] = {}
    for pdf in sorted(output_dir.glob("*.pdf")):
        files[pdf.name] = fix_space_cmap_pdf(pdf)
    return {"enabled": True, "files": files}

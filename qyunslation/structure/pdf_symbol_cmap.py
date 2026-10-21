# SPDX-License-Identifier: MPL-2.0
"""PLAN-084: give publisher symbol fonts a truthful ToUnicode before translation.

Some journal PDFs (Sage / ACDS ``Adv*`` fonts) draw ``±``, ``≥`` and ``©`` with glyphs stored under *other* WinAnsi
slots, and ship no ToUnicode: code 150 is the ``endash`` slot but draws ``±``; 135 (``daggerdbl``) draws ``≥``;
170 (``ordfeminine``) draws ``©``. Every extractor (BabelDOC, PyMuPDF, our table rebuild) then reads ``–`` / ``‡`` / ``ª``,
so the model translates ``mean ± SD`` as ``均值 – SD`` and ``≥16`` as ``‡16``. The glyph *names* inside the subset font
are the lying ones, so the fix is keyed on the font family, not derived from the font file.

Fail-open: any problem returns the original path untouched.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# Font family (subset prefix stripped) -> {WinAnsi code: real character}
SYMBOL_FONT_FIXES: dict[str, dict[int, str]] = {
    "AdvPSSymbol": {150: "\u00b1", 135: "\u2265"},  # ± ≥
    "AdvPSSym": {170: "\u00a9"},  # ©
}
_SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")


def symbol_fix_enabled() -> bool:
    raw = (os.environ.get("QYUNSLATION_FIX_SYMBOL_CMAP") or "1").strip().casefold()
    return raw not in {"0", "false", "off", "no"}


def font_family(base_font: str) -> str:
    return _SUBSET_PREFIX_RE.sub("", (base_font or "").strip().lstrip("/"))


def build_to_unicode(first: int, widths: list[int], overrides: dict[int, str]) -> bytes:
    """ToUnicode CMap for a one-byte simple font: used codes keep their cp1252 reading unless overridden."""
    pairs: dict[int, str] = {}
    for offset, width in enumerate(widths):
        code = first + offset
        if width:
            pairs[code] = overrides.get(code) or bytes([code]).decode("cp1252", errors="replace")
    for code, char in overrides.items():
        pairs.setdefault(code, char)
    body = "".join(f"<{code:02X}> <{ord(char):04X}>\n" for code, char in sorted(pairs.items()) if len(char) == 1)
    return (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
        f"{len(pairs)} beginbfchar\n{body}endbfchar\n"
        "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    ).encode("ascii")


def _widths(doc: Any, xref: int) -> tuple[int, list[int]]:
    first = doc.xref_get_key(xref, "FirstChar")
    widths = doc.xref_get_key(xref, "Widths")
    if first[0] != "int" or widths[0] not in {"array", "xref"}:
        return 0, []
    raw = widths[1] if widths[0] == "array" else doc.xref_object(int(widths[1].split()[0]), compressed=True)
    return int(first[1]), [int(float(x)) for x in re.findall(r"-?\d+(?:\.\d+)?", raw)]


def fix_symbol_fonts_pdf(src: Path, dst: Path) -> dict[str, Any]:
    """Write ``dst`` = ``src`` with ToUnicode on known symbol fonts. ``dst`` only exists when something changed."""
    summary: dict[str, Any] = {"patched_fonts": 0, "enabled": symbol_fix_enabled()}
    if not symbol_fix_enabled() or not src.is_file():
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
        doc = fitz.open(str(src))
    except Exception as exc:  # noqa: BLE001
        summary["error"] = type(exc).__name__
        return summary
    try:
        patched = 0
        for xref in range(1, doc.xref_length()):
            try:
                if doc.xref_get_key(xref, "Type")[1] != "/Font":
                    continue
                overrides = SYMBOL_FONT_FIXES.get(font_family(doc.xref_get_key(xref, "BaseFont")[1]))
                if not overrides or doc.xref_get_key(xref, "ToUnicode")[0] != "null":
                    continue
                first, widths = _widths(doc, xref)
                if not widths:
                    continue
                cmap = doc.get_new_xref()
                doc.update_object(cmap, "<< >>")
                doc.update_stream(cmap, build_to_unicode(first, widths, overrides))
                doc.xref_set_key(xref, "ToUnicode", f"{cmap} 0 R")
                patched += 1
            except Exception:  # noqa: BLE001
                continue
        summary["patched_fonts"] = patched
        if patched:
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_suffix(dst.suffix + ".symtmp")
            doc.save(str(tmp), garbage=0, deflate=True)
            tmp.replace(dst)
        return summary
    except Exception as exc:  # noqa: BLE001
        summary["error"] = type(exc).__name__
        return summary
    finally:
        doc.close()


def prepare_source_pdf(source: Path, workdir: Path) -> Path:
    """Return the PDF to translate: a fixed copy (same file name) under ``workdir`` or ``source`` itself."""
    try:
        dst = workdir / source.name
        if dst.resolve() == source.resolve():
            return source
        summary = fix_symbol_fonts_pdf(source, dst)
        if summary.get("patched_fonts") and dst.is_file():
            return dst
        if dst.exists():
            dst.unlink()
    except Exception:  # noqa: BLE001
        pass
    return source


__all__ = ["SYMBOL_FONT_FIXES", "build_to_unicode", "fix_symbol_fonts_pdf", "prepare_source_pdf"]

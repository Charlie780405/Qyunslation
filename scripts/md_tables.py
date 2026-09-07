#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-029a：期刊类 Markdown 表格结构化注入（复用 Hermes lit_tables 口径）。"""
from __future__ import annotations

import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Callable

HERMES_SCRIPTS = Path("/home/dev/Hermes/scripts")
if str(HERMES_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(HERMES_SCRIPTS))

from lit_tables import (  # noqa: E402
    ExtractedTable,
    caption_span,
    extract_tables_pdf,
    find_body_caption,
    is_slide_page,
    page_before,
    rows_to_markdown,
    trim_glued_rows,
)
from lit_tables import NUM_RE  # noqa: E402

logger = logging.getLogger("md_tables")

_SP = r"[^\S\n]"
_PIPE_CAPTION = re.compile(
    rf"^{_SP}*(?:[Tt]able|TABLE|表){_SP}*(?P<num>\d+)"
    rf"(?:{_SP}*[.．:：、|]{_SP}*|{_SP}+(?=[A-Z\u4e00-\u9fff]))[^\n]*$",
    re.M,
)

_PRESERVE_CELL = re.compile(
    r"^(?:"
    r"[-+±]?\d+(?:\.\d+)?(?:%|(?:\s*\([^)]*\))?)?"
    r"|n\s*=\s*\d+"
    r"|\(\d+(?:[.,]\d+)?%?\)"
    r"|\d+/\d+"
    r"|N/?A"
    r")$",
    re.I,
)


def _is_preserve_cell(text: str) -> bool:
    """纯数值/占位单元格不进 LLM，原样透传。"""
    t = (text or "").strip()
    if not t:
        return True
    if NUM_RE.fullmatch(t):
        return True
    return bool(_PRESERVE_CELL.fullmatch(t))


def _translate_rows(
    rows: list[list[str]],
    translate_fn: Callable[[list[str]], list[str]],
) -> list[list[str]]:
    unique: list[str] = []
    index: dict[str, int] = {}
    for row in rows:
        for cell in row:
            raw = (cell or "").strip()
            if not raw or _is_preserve_cell(raw):
                continue
            if raw not in index:
                index[raw] = len(unique)
                unique.append(raw)
    trans_map: dict[str, str] = {}
    if unique:
        try:
            zhs = translate_fn(unique)
            if len(zhs) != len(unique):
                raise ValueError(f"translate length {len(zhs)} != {len(unique)}")
            trans_map = dict(zip(unique, zhs))
        except Exception as exc:
            logger.warning("cell translate failed, keeping originals: %s", exc)
            trans_map = {k: k for k in unique}
    out: list[list[str]] = []
    for row in rows:
        new_row: list[str] = []
        for cell in row:
            raw = (cell or "").strip()
            if not raw or _is_preserve_cell(raw):
                new_row.append(cell)
            else:
                new_row.append(trans_map.get(raw, cell))
        out.append(new_row)
    return out


def _find_inject_anchor(body: str, tab: ExtractedTable):
    anchor = find_body_caption(body, tab)
    if anchor:
        return anchor
    ms = [m for m in _PIPE_CAPTION.finditer(body) if int(m.group("num")) == tab.number]
    if not ms:
        return None
    if tab.page:
        return min(ms, key=lambda m: abs((page_before(body, m.start()) or 0) - tab.page))
    return ms[0]


def _inject_one(body: str, tab: ExtractedTable, md: str) -> str:
    anchor = _find_inject_anchor(body, tab)
    if not anchor:
        return body
    cap, cap_end = caption_span(body, anchor)
    head, tail = body[: anchor.start()], body[cap_end:]
    stale = re.match(r"\n+(?:\|[^\n]*\|\n)+", tail)
    rest = (tail[stale.end() :] if stale else tail).lstrip("\n")
    return f"{head}{cap}\n\n{md}\n\n{rest}"


def _pdf_is_slide(src: Path) -> bool:
    import fitz

    with fitz.open(src) as doc:
        if not len(doc):
            return False
        return is_slide_page(doc[0])


def inject_translated_tables(
    md_text: str,
    src_pdf: Path | str,
    *,
    timeout_s: float = 60.0,
    translate_fn: Callable[[list[str]], list[str]] | None = None,
) -> tuple[str, dict]:
    """期刊 PDF：抽 ok 表 → 译非数值单元格 → 按题注注入 Markdown 管道表。"""
    src = Path(src_pdf)
    stats = {
        "ok": 0,
        "skipped_pending": 0,
        "skipped_unstructured": 0,
        "injected": 0,
        "elapsed": 0.0,
        "skipped_slide": False,
    }
    if not src.is_file() or not (md_text or "").strip():
        return md_text, stats
    if _pdf_is_slide(src):
        stats["skipped_slide"] = True
        return md_text, stats

    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(extract_tables_pdf, src, use_hpd=False)
            tables = fut.result(timeout=timeout_s)
    except FutTimeout:
        logger.warning("extract_tables_pdf timeout %.0fs: %s", timeout_s, src)
        stats["elapsed"] = time.time() - t0
        return md_text, stats
    except Exception as exc:
        logger.warning("extract_tables_pdf failed: %s", exc)
        stats["elapsed"] = time.time() - t0
        return md_text, stats

    if translate_fn is None:
        from letter_translate_prompt import translate_blocks

        def translate_fn(blocks: list[str]) -> list[str]:  # type: ignore[misc]
            glossary: list[tuple[str, str]] = []
            try:
                from kv_reinsert import _load_glossary

                glossary = _load_glossary()
            except Exception:
                pass
            return translate_blocks(blocks, glossary=glossary)

    body = md_text
    for tab in sorted(tables, key=lambda x: -x.number):
        if tab.table_status == "ok":
            stats["ok"] += 1
        elif tab.table_status == "pending":
            stats["skipped_pending"] += 1
            continue
        elif tab.table_status == "unstructured":
            stats["skipped_unstructured"] += 1
            continue
        else:
            continue
        if not tab.rows:
            continue
        rows = trim_glued_rows(tab.rows)
        zh_rows = _translate_rows(rows, translate_fn)
        md = rows_to_markdown(zh_rows)
        if not md:
            continue
        new_body = _inject_one(body, tab, md)
        if new_body != body:
            body = new_body
            stats["injected"] += 1

    stats["elapsed"] = time.time() - t0
    return body, stats

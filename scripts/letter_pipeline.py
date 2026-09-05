#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""正式书信扫描件：OCR debug → 跨页翻译 → 空白页重绘。生产 GUI 与 bench 共用。"""
from __future__ import annotations

import json
import logging
import unicodedata
from pathlib import Path

from graphic_reinsert import reinsert
from kv_reinsert import _item_zh, _load_glossary, reflow
from letter_translate_prompt import translate_blocks

logger = logging.getLogger(__name__)


def _bodies(page_info: dict) -> list[dict]:
    return [
        it
        for it in page_info.get("items") or []
        if it.get("role") in {"body", "section"} and (it.get("text") or "").strip()
    ]


def _ending(page_info: dict) -> str:
    items = _bodies(page_info)
    if not items:
        return ""
    return " ".join((items[-1].get("text") or "").split())[:400]


def _start(page_info: dict) -> str:
    items = _bodies(page_info)
    if not items:
        return ""
    return " ".join((items[0].get("text") or "").split())[:400]


def fill_page_zh(
    page_info: dict,
    *,
    prev: str,
    nxt: str,
    cache: dict[str, str],
    glossary: list[tuple[str, str]] | None = None,
) -> int:
    glossary = glossary if glossary is not None else _load_glossary()
    need: list[dict] = []
    for it in _bodies(page_info):
        en = " ".join((it.get("text") or "").split())
        if it.get("text_zh"):
            cache.setdefault(en, it["text_zh"])
            continue
        if en in cache:
            it["text_zh"] = cache[en]
        elif it.get("role") == "section":
            it["text_zh"] = _item_zh(en, "section", glossary)
        else:
            need.append(it)
    if not need:
        return 0
    ctx = ""
    if prev:
        ctx += f"Previous page ending:\n{prev}\n"
    if nxt:
        ctx += f"Next page start:\n{nxt}\n"
    zhs = translate_blocks(
        [" ".join((it.get("text") or "").split()) for it in need],
        extra_context=ctx,
        glossary=glossary,
    )
    for it, zh in zip(need, zhs):
        en = " ".join((it.get("text") or "").split())
        it["text_zh"] = zh
        cache[en] = zh
    return len(need)


def _fold(s: str) -> str:
    t = unicodedata.normalize("NFKC", "".join((s or "").split()))
    for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
        t = t.replace(dash, "-")
    return t


def missing_zh(pdf: Path, page_info: dict, page_index: int) -> list[str]:
    import pymupdf

    doc = pymupdf.open(pdf)
    if page_index >= len(doc):
        doc.close()
        return ["page-missing"]
    got = _fold(doc[page_index].get_text() or "")
    doc.close()
    miss: list[str] = []
    for it in page_info.get("items") or []:
        if it.get("role") not in {"body", "section"}:
            continue
        zh = _fold(it.get("text_zh") or "")
        if not zh or zh in {"美国食品与药品管理局", "CMC"}:
            continue
        key = zh[:8]
        if key and key not in got:
            miss.append(zh[:40])
    return miss


def translate_scanned_letter(
    ocr_pdf: Path,
    debug_json: Path,
    dest: Path,
    *,
    progress_cb=None,
) -> Path:
    """已 HPD OCR 的书信 PDF：写入 text_zh 后空白页 kv_reinsert。"""
    import pymupdf

    ocr_pdf = Path(ocr_pdf)
    debug_json = Path(debug_json)
    dest = Path(dest)
    data = json.loads(debug_json.read_text(encoding="utf-8"))
    pages = data.get("pages") or []
    if not pages:
        raise RuntimeError("letter_pipeline: debug 无 pages")
    glossary = _load_glossary()
    cache: dict[str, str] = {}
    n = len(pages)
    for i, page in enumerate(pages):
        if progress_cb:
            progress_cb(i + 1, n + 2, "translate")
        prev = _ending(pages[i - 1]) if i else ""
        nxt = _start(pages[i + 1]) if i + 1 < n else ""
        fill_page_zh(page, prev=prev, nxt=nxt, cache=cache, glossary=glossary)
    debug_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    src = pymupdf.open(ocr_pdf)
    out = pymupdf.open()
    for i in range(len(src)):
        r = src[i].rect
        out.new_page(width=r.width, height=r.height)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest)
    out.close()
    src.close()
    if progress_cb:
        progress_cb(n + 1, n + 2, "reflow")
    reflow(dest, debug_json)
    for i, page in enumerate(pages):
        miss = missing_zh(dest, page, i)
        if miss:
            raise RuntimeError(f"letter_pipeline page {i + 1} dropped: {miss[:3]}")
    mf = Path(str(ocr_pdf) + ".graphics.json")
    if mf.is_file():
        reinsert(dest, mf)
    if progress_cb:
        progress_cb(n + 2, n + 2, "done")
    logger.info("letter_pipeline → %s pages=%s", dest, n)
    return dest

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""正式书信扫描件：OCR debug → 跨页翻译 → 空白页重绘。生产 GUI 与 bench 共用。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from graphic_reinsert import reinsert
from kv_reinsert import _item_zh, _load_glossary, reflow
from letter_translate_prompt import translate_blocks

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CACHE_DEFAULT = Path.home() / ".cache" / "qyunslation" / "letter-zh.json"


def _cache_path() -> Path:
    raw = (os.environ.get("QYUNSLATION_LETTER_CACHE") or "").strip()
    return Path(raw) if raw else _CACHE_DEFAULT


def _cache_key(en: str) -> str:
    return hashlib.sha1(en.encode("utf-8")).hexdigest()


def _load_disk_cache() -> dict[str, str]:
    p = _cache_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception as exc:
        logger.warning("letter 缓存读取失败: %s", exc)
    return {}


def _save_disk_cache(cache: dict[str, str]) -> None:
    p = _cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # 存 sha1→zh；同时保留一份 en→zh 映射的 sha 表
        payload = {k: v for k, v in cache.items() if k and v}
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        tmp.replace(p)
    except Exception as exc:
        logger.warning("letter 缓存写入失败: %s", exc)


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
    lock: threading.Lock | None = None,
) -> int:
    glossary = glossary if glossary is not None else _load_glossary()
    need: list[dict] = []
    for it in _bodies(page_info):
        en = " ".join((it.get("text") or "").split())
        key = _cache_key(en)
        if it.get("text_zh"):
            zh = it["text_zh"]
            if lock:
                with lock:
                    cache.setdefault(key, zh)
                    cache.setdefault(en, zh)
            else:
                cache.setdefault(key, zh)
                cache.setdefault(en, zh)
            continue
        hit = None
        if lock:
            with lock:
                hit = cache.get(key) or cache.get(en)
        else:
            hit = cache.get(key) or cache.get(en)
        if hit:
            it["text_zh"] = hit
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
        if not _CJK_RE.search(zh or ""):
            zh = _item_zh(en, it.get("role") or "body", glossary)
        it["text_zh"] = zh
        if _CJK_RE.search(zh or ""):
            key = _cache_key(en)
            if lock:
                with lock:
                    cache[key] = zh
                    cache[en] = zh
            else:
                cache[key] = zh
                cache[en] = zh
        else:
            logger.warning("letter_pipeline 未译 %s", en[:48])
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
        zh = _fold(it.get("text_zh") or "").rstrip(":：、.")
        if not zh or not _CJK_RE.search(zh):
            continue
        if zh in {"美国食品与药品管理局", "CMC", "引言", "背景"}:
            continue
        if it.get("role") == "section" and len(zh) <= 8:
            continue
        key = zh[:8]
        if key and key not in got:
            miss.append(zh[:40])
    return miss


def _letter_workers() -> int:
    try:
        return max(1, int(os.environ.get("QYUNSLATION_LETTER_WORKERS", "4") or "4"))
    except ValueError:
        return 4


def _reinsert_kinds() -> set[str] | None:
    if (os.environ.get("QYUNSLATION_LETTER_GRAPHICS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return None
    return {"logo", "stamp"}


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
    cache: dict[str, str] = _load_disk_cache()
    lock = threading.Lock()
    n = len(pages)
    workers = min(_letter_workers(), max(n, 1))
    done = [0]

    def _tick(frac: float, desc: str) -> None:
        logger.info("%s", desc)
        if progress_cb:
            progress_cb(frac, desc)

    # 全局去重：先把已有 text_zh / 磁盘缓存灌进各页，收集仍需 LLM 的页
    def _work(i: int) -> int:
        prev = _ending(pages[i - 1]) if i else ""
        nxt = _start(pages[i + 1]) if i + 1 < n else ""
        n_need = fill_page_zh(
            pages[i],
            prev=prev,
            nxt=nxt,
            cache=cache,
            glossary=glossary,
            lock=lock,
        )
        with lock:
            done[0] += 1
            cur = done[0]
        _tick(cur / max(n, 1) * 0.88, f"②翻译 {cur}/{n} 页")
        return n_need

    _tick(0.0, f"②翻译 0/{n} 页")
    if workers <= 1 or n <= 1:
        for i in range(n):
            _work(i)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_work, i) for i in range(n)]
            for fut in as_completed(futs):
                fut.result()
    _save_disk_cache(
        {k: v for k, v in cache.items() if len(k) == 40 and all(c in "0123456789abcdef" for c in k)}
    )
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
    _tick(0.92, "③排版重绘")
    reflow(dest, debug_json)
    warnings: list[dict] = []
    for i, page in enumerate(pages):
        miss = missing_zh(dest, page, i)
        if miss:
            logger.error("letter_pipeline page %s dropped: %s", i + 1, miss[:3])
            warnings.append({"page": i + 1, "dropped": miss})
    if warnings:
        warn_path = Path(str(dest) + ".warnings.json")
        warn_path.write_text(
            json.dumps(warnings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    mf = Path(str(ocr_pdf) + ".graphics.json")
    if mf.is_file():
        reinsert(dest, mf, kinds=_reinsert_kinds())
    _tick(1.0, "完成")
    logger.info("letter_pipeline → %s pages=%s warnings=%s", dest, n, len(warnings))
    return dest

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""剩余扫描页：HPD OCR → qwen3.6:35b-a3b 译文 → 空白页重绘。版式以 kv_reinsert 为准。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from graphic_reinsert import reinsert  # noqa: E402
from hpd_ocr import ocr_pdf_with_hpd  # noqa: E402
from kv_reinsert import _load_glossary, reflow  # noqa: E402
from letter_translate_prompt import translate_blocks  # noqa: E402
from proper_nouns import harvest  # noqa: E402

WORK = Path("/home/dev/pdf2zh/bench/007")
SRC = Path(
    "/home/dev/pdf2zh/pdf2zh_files/5fa54bcf-4843-4e97-8cd0-85c797fa9b5d/"
    "FDA responses on PIND.pdf"
)
DELIV = ROOT / "deliverables" / "plan-010-fidelity"
CACHE = WORK / "zh-cache.json"


def _extract(page_1based: int) -> Path:
    import pymupdf

    dest = WORK / f"page{page_1based}.pdf"
    src = pymupdf.open(SRC)
    out = pymupdf.open()
    out.insert_pdf(src, from_page=page_1based - 1, to_page=page_1based - 1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest)
    out.close()
    src.close()
    return dest


def _ocr(page_1based: int) -> tuple[Path, Path]:
    pdf = _extract(page_1based)
    dest = WORK / f"page{page_1based}.hpd-ocr.pdf"
    ocr_pdf_with_hpd(pdf, dest, profile="letter", aggressive=True, min_font_size=8.0)
    harvest(pdf)
    return dest, Path(str(dest) + ".hpd-debug.json")


def _load_cache() -> dict[str, str]:
    if CACHE.is_file():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _page_bodies(debug: dict) -> list[dict]:
    items = (debug.get("pages") or [{}])[0].get("items") or []
    return [
        it
        for it in items
        if it.get("role") in {"body", "section"} and (it.get("text") or "").strip()
    ]


def _fill_zh(debug: dict, *, prev: str, nxt: str, cache: dict[str, str]) -> int:
    glossary = _load_glossary()
    items = _page_bodies(debug)
    need: list[dict] = []
    for it in items:
        en = " ".join((it.get("text") or "").split())
        if en in cache:
            it["text_zh"] = cache[en]
        elif it.get("role") == "section":
            from kv_reinsert import _item_zh

            it["text_zh"] = _item_zh(en, "section", glossary)
        else:
            need.append(it)
    if need:
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


def _missing_zh(pdf: Path, debug: dict) -> list[str]:
    import unicodedata
    import pymupdf

    def fold(s: str) -> str:
        t = unicodedata.normalize("NFKC", "".join((s or "").split()))
        for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
            t = t.replace(dash, "-")
        return t

    doc = pymupdf.open(pdf)
    got = fold(doc[0].get_text() or "")
    doc.close()
    miss: list[str] = []
    for it in (debug.get("pages") or [{}])[0].get("items") or []:
        if it.get("role") not in {"body", "section"}:
            continue
        zh = fold(it.get("text_zh") or "")
        if not zh or zh in {"美国食品与药品管理局", "CMC"}:
            continue
        key = zh[:8]
        if key and key not in got:
            miss.append(zh[:40])
    return miss


def _render(page_1based: int, debug_path: Path) -> Path:
    import pymupdf

    src = pymupdf.open(WORK / f"page{page_1based}.pdf")
    out = pymupdf.open()
    r = src[0].rect
    out.new_page(width=r.width, height=r.height)
    work = WORK / "out-rest" / f"page{page_1based}.work.pdf"
    work.parent.mkdir(parents=True, exist_ok=True)
    out.save(work)
    out.close()
    src.close()
    reflow(work, debug_path)
    miss = _missing_zh(work, json.loads(debug_path.read_text(encoding="utf-8")))
    if miss:
        raise RuntimeError(f"page {page_1based} dropped: {miss[:3]}")
    mf = WORK / f"page{page_1based}.hpd-ocr.pdf.graphics.json"
    if mf.is_file():
        reinsert(work, mf)
    png = DELIV / f"letter.page{page_1based}.mono.png"
    pdf = DELIV / f"letter.page{page_1based}.mono.pdf"
    DELIV.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(work)
    doc[0].get_pixmap(dpi=130).save(png)
    doc.save(pdf)
    doc.close()
    return png


def _ending(debug: dict) -> str:
    bodies = _page_bodies(debug)
    if not bodies:
        return ""
    return " ".join((bodies[-1].get("text") or "").split())[:400]


def _start(debug: dict) -> str:
    bodies = _page_bodies(debug)
    if not bodies:
        return ""
    return " ".join((bodies[0].get("text") or "").split())[:400]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-page", type=int, default=4)
    ap.add_argument("--to-page", type=int, default=20)
    args = ap.parse_args()
    cache = _load_cache()
    debugs: dict[int, dict] = {}
    paths: dict[int, Path] = {}
    for n in range(args.from_page, args.to_page + 1):
        print(f"== OCR page {n} ==", flush=True)
        _ocr_pdf, dbg = _ocr(n)
        paths[n] = dbg
        debugs[n] = json.loads(dbg.read_text(encoding="utf-8"))
    # 邻页英文上下文：含已有 page3
    extra = {}
    p3 = WORK / "page3.hpd-ocr.pdf.hpd-debug.json"
    if p3.is_file():
        extra[3] = json.loads(p3.read_text(encoding="utf-8"))
    for n in range(args.from_page, args.to_page + 1):
        prev = _ending(debugs.get(n - 1) or extra.get(n - 1) or {})
        nxt_dbg = debugs.get(n + 1)
        nxt = _start(nxt_dbg) if nxt_dbg else ""
        print(f"== translate page {n} ==", flush=True)
        called = _fill_zh(debugs[n], prev=prev, nxt=nxt, cache=cache)
        paths[n].write_text(json.dumps(debugs[n], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _save_cache(cache)
        png = _render(n, paths[n])
        print(f"wrote {png} ollama_blocks={called}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

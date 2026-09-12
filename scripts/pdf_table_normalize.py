#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-047e：表格区域字号归一 + 漏译补翻（不依赖结构重建）。"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_WHITELIST = {
    "iga",
    "easi",
    "ada",
    "nab",
    "nrs",
    "q2w",
    "q4w",
    "bsa",
    "ecztra",
    "doi",
    "http",
    "https",
    "table",
    "figure",
    "leo",
    "pharma",
}


def _p75(values: list[float]) -> float:
    if not values:
        return 8.0
    ordered = sorted(values)
    idx = int(round(0.75 * (len(ordered) - 1)))
    return float(ordered[idx])


def _is_whitelisted(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?%?", t):
        return True
    if re.fullmatch(r"[<>≤≥]=?\s*\d+(?:\.\d+)?%?", t):
        return True
    if t.upper() in {"NA", "N/A", "ND", "NR", "NS", "<", ">", "≤", "≥"}:
        return True
    if re.fullmatch(r"n\s*/\s*N", t, re.I):
        return True
    words = _LATIN_WORD_RE.findall(t)
    if not words:
        return True
    return all(w.lower() in _WHITELIST for w in words)


def normalize_table_page(
    page,
    rect,
    *,
    translator=None,
    min_ratio: float = 0.75,
    allow_translate: bool = True,
) -> dict:
    """对 page 上 rect 区域内的文字做字号归一，并补翻残留拉丁。

    PLAN-048e：按角色近似分带——区域顶部 22% 当表头取 p75，其余当表体取 p75。
    返回 {resized, translated, skipped, sizes_before, sizes_after, latin_residue_rate}。
    """
    import pymupdf

    clip = pymupdf.Rect(rect)
    d = page.get_text("dict", clip=clip)
    sizes: list[float] = []
    header_sizes: list[float] = []
    body_sizes: list[float] = []
    spans: list[dict] = []
    band = float(clip.y0) + float(clip.height) * 0.22
    for block in d.get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                text = (span.get("text") or "").strip()
                if not text:
                    continue
                size = float(span.get("size") or 0)
                bbox = span.get("bbox")
                if not bbox or size <= 0:
                    continue
                sizes.append(size)
                cy = (float(bbox[1]) + float(bbox[3])) / 2.0
                if cy <= band:
                    header_sizes.append(size)
                else:
                    body_sizes.append(size)
                spans.append(
                    {
                        "text": text,
                        "size": size,
                        "bbox": tuple(bbox),
                        "font": span.get("font") or "helv",
                        "color": span.get("color"),
                        "flags": span.get("flags") or 0,
                        "is_header": cy <= band,
                    }
                )
    if not spans:
        return {
            "resized": 0,
            "translated": 0,
            "skipped": 0,
            "sizes_before": [],
            "sizes_after": [],
            "latin_residue_rate": 0.0,
        }

    header_target = _p75(header_sizes or sizes)
    body_target = _p75(body_sizes or sizes)
    resized = 0
    translated = 0
    rewrite: list[dict] = []
    for sp in spans:
        text = sp["text"]
        size = sp["size"]
        target = header_target if sp.get("is_header") else body_target
        floor = max(6.0, target * min_ratio)
        new_text = text
        new_size = size
        if size < floor or abs(size - target) > 0.75:
            new_size = target
            if abs(size - target) > 0.05:
                resized += 1
        # 漏译：纯拉丁且不在白名单。PLAN-049c 文献窄表只调字号。
        if (
            allow_translate
            and not _CJK_RE.search(text)
            and _LATIN_WORD_RE.search(text)
            and not _is_whitelisted(text)
        ):
            if translator is not None:
                try:
                    zh = translator(text)
                    if isinstance(zh, dict):
                        zh = next(iter(zh.values()), "")
                    zh = (zh or "").strip()
                    if zh and _CJK_RE.search(zh):
                        new_text = zh
                        translated += 1
                        if new_size < floor:
                            new_size = target
                except Exception as exc:
                    logger.warning("table normalize translate failed: %s", exc)
        if new_text != text or abs(new_size - size) > 0.05:
            rewrite.append({**sp, "new_text": new_text, "new_size": new_size})

    for item in rewrite:
        x0, y0, x1, y1 = item["bbox"]
        pad = 0.4
        page.add_redact_annot(
            pymupdf.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad),
            fill=(1, 1, 1),
        )
    if rewrite:
        page.apply_redactions(images=0, graphics=0)

    after_sizes: list[float] = []
    for item in rewrite:
        x0, y0, x1, y1 = item["bbox"]
        new_size = float(item["new_size"])
        text = item["new_text"]
        tw = pymupdf.get_text_length(text, fontname="china-s", fontsize=new_size)
        box_w = max(1.0, x1 - x0)
        while tw > box_w * 1.05 and new_size > 6.0:
            new_size -= 0.5
            tw = pymupdf.get_text_length(text, fontname="china-s", fontsize=new_size)
        after_sizes.append(new_size)
        baseline = y1 - new_size * 0.15
        try:
            page.insert_text(
                (x0, baseline),
                text,
                fontsize=new_size,
                fontname="china-s",
                color=(0, 0, 0),
            )
        except Exception:
            page.insert_text(
                (x0, baseline),
                text,
                fontsize=new_size,
                color=(0, 0, 0),
            )

    d2 = page.get_text("dict", clip=clip)
    total = 0
    latin = 0
    final_sizes: list[float] = []
    for block in d2.get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                text = (span.get("text") or "").strip()
                if not text:
                    continue
                total += 1
                final_sizes.append(float(span.get("size") or 0))
                if (
                    not _CJK_RE.search(text)
                    and _LATIN_WORD_RE.search(text)
                    and not _is_whitelisted(text)
                ):
                    latin += 1

    return {
        "resized": resized,
        "translated": translated,
        "skipped": 0,
        "sizes_before": sorted(set(round(s, 2) for s in sizes)),
        "sizes_after": sorted(set(round(s, 2) for s in (final_sizes or after_sizes or sizes))),
        "latin_residue_rate": (latin / total) if total else 0.0,
    }


def normalize_failed_tables(
    doc_path: Path,
    manifest,
    *,
    translator=None,
    x_min_frac: float = 0.0,
) -> Path | None:
    """对结构链失败的表区域做归一；写出 .tblnorm.pdf，成功则返回路径。"""
    import pymupdf
    from qyunslation.structure.models import ExecutionStatus, ObjectType

    src = Path(doc_path)
    doc = pymupdf.open(src)
    changed = False
    try:
        for obj in manifest.objects:
            if obj.type is not ObjectType.TABLE:
                continue
            status = getattr(obj, "execution_status", None)
            if status not in {
                ExecutionStatus.FAILED_HARD,
                ExecutionStatus.FAILED_SOFT,
                ExecutionStatus.EXPLICITLY_SKIPPED,
            }:
                # 也处理仍 PENDING 但未写回的
                if status is ExecutionStatus.TRANSLATED:
                    continue
            try:
                page_no = int(str(obj.canvas_id).split(":")[-1])
            except Exception:
                continue
            page_index = page_no - 1
            if page_index < 0 or page_index >= len(doc):
                continue
            box = obj.bbox
            x0, y0, x1, y1 = float(box.x0), float(box.y0), float(box.x1), float(box.y1)
            page = doc[page_index]
            width = float(page.rect.width)
            if x_min_frac > 0:
                x0 = max(x0, width * x_min_frac)
            stats = normalize_table_page(
                page, (x0, y0, x1, y1), translator=translator
            )
            logger.info(
                "table normalize %s page=%d resized=%d translated=%d sizes %s -> %s residue=%.2f",
                obj.semantic_id,
                page_no,
                stats["resized"],
                stats["translated"],
                stats["sizes_before"],
                stats["sizes_after"],
                stats["latin_residue_rate"],
            )
            if stats["resized"] or stats["translated"]:
                changed = True
        if not changed:
            return None
        out = src.with_name(src.stem + ".tblnorm.pdf")
        doc.save(out, deflate=True, garbage=3)
        return out
    finally:
        doc.close()


if __name__ == "__main__":
    import sys

    print("use normalize_failed_tables from pdf_table_translate", file=sys.stderr)
    sys.exit(0)

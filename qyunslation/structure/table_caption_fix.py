# SPDX-License-Identifier: MPL-2.0
"""PLAN-084: 表题深色标签（白字黑底的 ``TABLE 1.``）译后修复。

BabelDOC 把「标签 + 题名」合成一段，整段用黑字写：``表 1. 基线特征`` 的「表 1.」落在黑色标签底上，黑底黑字看不见，
题名前半又压在黑底上。这里在译文页上擦掉该行，标签用白字写回黑底内，题名按原文位置用深色写回。
只在原文该位置确有「深色底 + 白字标签」且译文该行真是深色字时才动手；任何不确定都不改。
"""
from __future__ import annotations

import re
from typing import Any

_LABEL_RE = re.compile(r"^\s*(表\s*\d+)\s*[.．。]?\s*(.*?)\s*$", re.S)
_BOLD_FACE = "SourceHanSerifCN-Bold"


def _luma(rgb) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _rgb(color: int) -> tuple[float, float, float]:
    return (((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255)


def _fitz():
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except ImportError:
        import fitz  # type: ignore[import-not-found,no-redef]
    return fitz


def _dark_label_rect(origin_page, box):
    """表框正上方的深色小矩形（标签底）。"""
    best = None
    for item in origin_page.get_drawings():
        fill = item.get("fill")
        rect = item.get("rect")
        if not fill or len(fill) < 3 or rect is None or rect.is_empty:
            continue
        if _luma(fill) > 0.35 or not (15 <= rect.width <= 160 and 6 <= rect.height <= 26):
            continue
        if not (box[1] - 22 <= rect.y1 <= box[1] + 4) or not (box[0] - 8 <= rect.x0 <= box[0] + 60):
            continue
        if best is None or rect.y1 > best.y1:
            best = rect
    return best


def _source_label_and_caption(origin_page, bar):
    fitz = _fitz()
    band = fitz.Rect(bar.x0 - 2, bar.y0 - 1, origin_page.rect.width, bar.y1 + 1)
    label: dict[str, Any] | None = None
    caption: dict[str, Any] | None = None
    for block in origin_page.get_text("rawdict", clip=band).get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = "".join(ch["c"] for ch in span.get("chars", [])).strip()
                if not text:
                    continue
                bbox = fitz.Rect(span["bbox"])
                if int(span.get("color", 0)) == 0xFFFFFF and bbox.x1 <= bar.x1 + 2 and label is None:
                    label = {"x": float(span["chars"][0]["origin"][0]), "y": float(span["chars"][0]["origin"][1]), "size": float(span["size"])}
                elif label is not None and bbox.x0 >= bar.x1 - 1 and caption is None:
                    caption = {
                        "x": float(span["chars"][0]["origin"][0]),
                        "size": float(span["size"]),
                        "color": int(span.get("color", 0)),
                    }
    return label, caption


def repair_dark_caption_label(page, origin_page, box, *, x_min_frac: float | None = None) -> bool:
    fitz = _fitz()
    from qyunslation.structure.pdf_dropcap import _subset

    bar = _dark_label_rect(origin_page, box)
    if bar is None:
        return False
    label, caption = _source_label_and_caption(origin_page, bar)
    if label is None:
        return False
    dx = float(page.rect.width) * float(x_min_frac) if x_min_frac else 0.0
    band = fitz.Rect(bar.x0 - 2 + dx, bar.y0 - 1.5, page.rect.width, bar.y1 + 1.5)
    spans: list[dict[str, Any]] = []
    for block in page.get_text("dict", clip=band).get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if str(span.get("text") or "").strip():
                    spans.append(span)
    if not spans:
        return False
    # 只处理「落在深色底上的深色字」：已经是白字或不在底上就不动
    on_bar = [s for s in spans if fitz.Rect(s["bbox"]).intersects(fitz.Rect(bar.x0 + dx, bar.y0, bar.x1 + dx, bar.y1))]
    if not on_bar or any(_luma(_rgb(int(s.get("color", 0)))) > 0.6 for s in on_bar):
        return False
    text = "".join(str(s.get("text") or "") for s in sorted(spans, key=lambda s: s["bbox"][0]))
    # BabelDOC 把词间空白写成 U+0003 之类的控制符（空格字形 ToUnicode），先还原成空格。
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    match = _LABEL_RE.match(text)
    if not match:
        return False
    number = re.sub(r"\s+", " ", match.group(1)).strip()
    label_text, caption_text = f"{number}.", re.sub(r"\s+", " ", match.group(2)).strip()
    union = fitz.Rect(spans[0]["bbox"])
    for s in spans[1:]:
        union |= fitz.Rect(s["bbox"])
    chars = set(label_text) | set(caption_text) | {" "}
    path = _subset(_BOLD_FACE, chars)
    if path is None:
        return False
    page.add_redact_annot(fitz.Rect(union.x0 - 0.3, union.y0 + 0.5, union.x1 + 0.3, union.y1 - 0.5), fill=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    page.insert_font(fontname="qcap", fontfile=str(path))
    font = fitz.Font(fontfile=str(path))
    size = float(label["size"])
    bar_w = bar.width - 4.0
    while size > 6.0 and font.text_length(label_text, fontsize=size) > bar_w:
        size -= 0.5
    page.insert_text((bar.x0 + dx + 2.5, label["y"]), label_text, fontname="qcap", fontsize=size, color=(1, 1, 1))
    if caption_text:
        csize = float((caption or {}).get("size") or label["size"])
        x = float((caption or {}).get("x") or (bar.x1 + 5)) + dx
        right = float(box[2]) + dx
        while csize > 7.0 and x + font.text_length(caption_text, fontsize=csize) > right:
            csize -= 0.5
        color = _rgb(int((caption or {}).get("color", 0x231F20)))
        page.insert_text((x, label["y"]), caption_text, fontname="qcap", fontsize=csize, color=color)
    return True

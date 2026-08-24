# SPDX-License-Identifier: MPL-2.0
"""拍照/扫描 PDF → 泰州 HPD 铺不可见文字层。供 pdf2zh 进程直接 import。"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

HPD_URL = "http://100.67.66.123:8120"
CJK_FONT = Path(os.environ.get("QYUNSLATION_FONT", "/home/dev/.fonts/NotoSansSC.ttf"))
_BLOCK_RE = re.compile(
    r"<BLOCK>(?P<type>\w+)\s+\[(?P<x1>\d+),\s*(?P<y1>\d+),\s*(?P<x2>\d+),\s*(?P<y2>\d+)\]"
    r"(?:<CHILD>(?P<text>.+))?$"
)
_TAG_RE = re.compile(r"<[^>]+>")
_TR_RE = re.compile(r"<tr>(.*?)</tr>", re.I | re.S)
_TD_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)


def _parse(url: str, image_b64: str, timeout: int = 180) -> str:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/parse",
        data=json.dumps({"image_b64": image_b64}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data.get("markdown") or ""


def _clean_ocr_text(text: str) -> str:
    """去掉 HPD 表格 HTML，保留单元格中文。"""
    text = (
        text.replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    text = _TAG_RE.sub(" ", text)
    return " ".join(text.split()).strip()


def _table_cells(html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in _TR_RE.findall(html):
        cells = [_clean_ocr_text(c) for c in _TD_RE.findall(tr)]
        if any(cells):
            rows.append(cells)
    return rows


def _split_table_box(
    x1: int, y1: int, x2: int, y2: int, rows: list[list[str]]
) -> list[tuple[int, int, int, int, str]]:
    """按行列把整表 bbox 切成单元格，避免 <table> 整段进文字层。"""
    if not rows:
        return []
    height = max(y2 - y1, 8)
    width = max(x2 - x1, 8)
    weights = [max(1, sum(len(c) for c in row)) for row in rows]
    total = sum(weights)
    out: list[tuple[int, int, int, int, str]] = []
    y = float(y1)
    for i, row in enumerate(rows):
        rh = height * weights[i] / total
        ncols = max(len(row), 1)
        fracs = [0.22, 0.78] if ncols == 2 else [1.0 / ncols] * ncols
        x = float(x1)
        for j, cell in enumerate(row):
            cw = width * fracs[j]
            if cell:
                out.append((int(x), int(y), int(x + cw), int(y + rh), cell))
            x += cw
        y += rh
    return out


def _blocks(raw: str) -> list[tuple[int, int, int, int, str]]:
    out: list[tuple[int, int, int, int, str]] = []
    for line in raw.splitlines():
        m = _BLOCK_RE.match(line.strip())
        if not m:
            continue
        text = (m.group("text") or "").strip()
        if not text or text == "[Non-Text]":
            continue
        box = (
            int(m.group("x1")),
            int(m.group("y1")),
            int(m.group("x2")),
            int(m.group("y2")),
        )
        if "<table" in text.lower():
            cells = _split_table_box(*box, _table_cells(text))
            if cells:
                out.extend(cells)
                continue
        cleaned = _clean_ocr_text(text)
        if cleaned:
            out.append((*box, cleaned))
    return out


def _cjk_fontname(page) -> str:
    if CJK_FONT.is_file():
        page.insert_font(fontname="noto", fontfile=str(CJK_FONT))
        return "noto"
    return "china-ss"


def pdf_needs_hpd(src: Path, min_chars: int = 80) -> bool:
    import pymupdf

    doc = pymupdf.open(src)
    try:
        text = "".join((p.get_text() or "") for p in doc)
    finally:
        doc.close()
    return len(text.strip()) < min_chars


def ocr_pdf_with_hpd(
    src: Path,
    dest: Path | None = None,
    *,
    dpi: int = 150,
    progress_cb=None,
) -> Path:
    import pymupdf

    src = Path(src)
    dest = dest or src.with_name(f"{src.stem}.hpd-ocr.pdf")
    dest = Path(dest)
    doc = pymupdf.open(src)
    written = 0
    total = len(doc)
    for i, page in enumerate(doc):
        if progress_cb:
            progress_cb(i + 1, total)
        pix = page.get_pixmap(dpi=dpi)
        b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode()
        try:
            raw = _parse(HPD_URL, b64)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            logger.warning("HPD 第 %s 页失败: %s", i + 1, exc)
            continue
        blocks = _blocks(raw)
        pw, ph = page.rect.width, page.rect.height
        sx, sy = pw / max(pix.width, 1), ph / max(pix.height, 1)
        max_x = max((b[2] for b in blocks), default=0)
        max_y = max((b[3] for b in blocks), default=0)
        if max(max_x, max_y) <= 1000 and (pix.width > 1200 or pix.height > 1200):
            sx, sy = pw / 1000.0, ph / 1000.0
        fontname = _cjk_fontname(page)
        for x1, y1, x2, y2, text in blocks:
            box = pymupdf.Rect(x1 * sx, y1 * sy, max(x2 * sx, x1 * sx + 8), max(y2 * sy, y1 * sy + 8))
            try:
                box_w = max(box.x1 - box.x0, 8)
                box_h = max(box.y1 - box.y0, 8)
                fs = min(12.0, box_h * 0.45, box_w / max(len(text), 1) * 1.8)
                page.insert_textbox(
                    box,
                    text,
                    fontname=fontname,
                    fontsize=max(5.0, fs),
                    render_mode=3,
                    overlay=True,
                )
                written += 1
            except Exception:
                continue
        logger.info("HPD 第 %s 页 %s 块", i + 1, len(blocks))
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)
    doc.close()
    if written == 0:
        raise RuntimeError("HPD 未识别到文字")
    return dest

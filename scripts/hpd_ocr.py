# SPDX-License-Identifier: MPL-2.0
"""拍照/扫描 PDF → 泰州 HPD 铺不可见文字层。供 pdf2zh 进程直接 import。"""
from __future__ import annotations

import base64
import json
import logging
import math
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

_LINE_FACTOR = 1.25
_FS_FLOOR = 7.0
_FS_CEIL = 28.0
_EXPAND_GAP = 2.0


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
    """去掉 HPD 表格 HTML，保留单元格中文；剥离易弄坏 LLM JSON 的反斜杠。"""
    text = (
        text.replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    text = _TAG_RE.sub(" ", text)
    # BabelDOC LLM 批译输出 JSON；OCR 里的 \( \) \n 等会触发 Invalid \escape
    text = text.replace("\\", "")
    text = text.replace("\u00a0", " ").replace("\u2011", "-").replace("\u2013", "-")
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


def _pymupdf_font():
    import pymupdf

    if CJK_FONT.is_file():
        return pymupdf.Font(fontfile=str(CJK_FONT))
    return pymupdf.Font("china-ss")


def _fit_fontsize(font, text: str, box_w: float, box_h: float,
                  lo: float = _FS_FLOOR, hi: float = _FS_CEIL) -> float:
    """二分求最大可容纳字号（按宽度换行后总高度须 ≤ box_h）。"""
    usable_w = max(box_w - 2.0, 4.0)
    if usable_w <= 0 or box_h <= 0 or not text:
        return lo
    best = lo
    for _ in range(14):
        mid = (lo + hi) / 2.0
        try:
            tw = float(font.text_length(text, fontsize=mid))
        except Exception:
            tw = len(text) * mid * 0.55
        lines = max(1, math.ceil(tw / usable_w))
        if lines * mid * _LINE_FACTOR <= box_h:
            best, lo = mid, mid
        else:
            hi = mid
    return best


def _needed_height(font, text: str, box_w: float, fs: float = _FS_FLOOR) -> float:
    usable_w = max(box_w - 2.0, 4.0)
    try:
        tw = float(font.text_length(text, fontsize=fs))
    except Exception:
        tw = len(text) * fs * 0.55
    lines = max(1, math.ceil(tw / usable_w))
    return lines * fs * _LINE_FACTOR


def _scale_axes(
    pw: float, ph: float, pix_w: int, pix_h: int, max_x: int, max_y: int
) -> tuple[float, float, str]:
    """按轴独立归一化；返回 (sx, sy, mode)。"""
    sx = pw / max(pix_w, 1)
    sy = ph / max(pix_h, 1)
    mode = "pixel"
    use_nx = max_x <= 1000 and pix_w > 1200
    use_ny = max_y <= 1000 and pix_h > 1200
    if use_nx:
        sx = pw / 1000.0
        mode = "norm-x" if not use_ny else "norm-xy"
    if use_ny:
        sy = ph / 1000.0
        mode = "norm-y" if not use_nx else "norm-xy"
    return sx, sy, mode


def _expand_boxes(
    boxes: list[tuple[float, float, float, float, str]],
    font,
    page_h: float,
) -> list[tuple[float, float, float, float, str, float, bool]]:
    """盒高不足时向下扩展（受下一块 y1 限制），再求字号。"""
    ordered = sorted(enumerate(boxes), key=lambda it: (it[1][1], it[1][0]))
    out: list[tuple[float, float, float, float, str, float, bool] | None] = [None] * len(boxes)
    for idx, (orig_i, (x0, y0, x1, y1, text)) in enumerate(ordered):
        box_w = max(x1 - x0, 8.0)
        box_h = max(y1 - y0, 8.0)
        expanded = False
        need = _needed_height(font, text, box_w, _FS_FLOOR) * 1.2
        if need > box_h + 0.5:
            limit = page_h - _EXPAND_GAP
            if idx + 1 < len(ordered):
                next_y0 = ordered[idx + 1][1][1]
                # 仅当大致同列时才用下一块约束
                nx0, _, nx1, _, _ = ordered[idx + 1][1]
                overlap = min(x1, nx1) - max(x0, nx0)
                if overlap > box_w * 0.3:
                    limit = min(limit, next_y0 - _EXPAND_GAP)
            new_y1 = min(y0 + need, limit)
            if new_y1 > y1:
                y1 = new_y1
                box_h = max(y1 - y0, 8.0)
                expanded = True
        fs = _fit_fontsize(font, text, box_w, box_h)
        if fs <= _FS_FLOOR + 0.05:
            logger.warning(
                "HPD 字号触地板: chars=%s box=%.1fx%.1f fs=%.2f",
                len(text),
                box_w,
                box_h,
                fs,
            )
        out[orig_i] = (x0, y0, x1, y1, text, fs, expanded)
    return [b for b in out if b is not None]  # type: ignore[misc]


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
    debug = os.environ.get("QYUNSLATION_HPD_DEBUG", "").strip() in {"1", "true", "yes"}
    debug_pages: list[dict] = []
    doc = pymupdf.open(src)
    written = 0
    floor_hits = 0
    total = len(doc)
    font = _pymupdf_font()
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
        max_x = max((b[2] for b in blocks), default=0)
        max_y = max((b[3] for b in blocks), default=0)
        sx, sy, scale_mode = _scale_axes(pw, ph, pix.width, pix.height, max_x, max_y)

        def _apply_scale(
            sx_: float, sy_: float
        ) -> list[tuple[float, float, float, float, str]]:
            out: list[tuple[float, float, float, float, str]] = []
            for x1, y1, x2, y2, text in blocks:
                out.append(
                    (
                        x1 * sx_,
                        y1 * sy_,
                        max(x2 * sx_, x1 * sx_ + 8),
                        max(y2 * sy_, y1 * sy_ + 8),
                        text,
                    )
                )
            return out

        scaled = _apply_scale(sx, sy)
        if scaled and any(b[2] > pw + 1 or b[3] > ph + 1 for b in scaled):
            logger.warning("HPD 第 %s 页 box 越界 mode=%s，改用像素映射", i + 1, scale_mode)
            sx, sy = pw / max(pix.width, 1), ph / max(pix.height, 1)
            scale_mode = "pixel-fallback"
            scaled = _apply_scale(sx, sy)
        if scaled and len(scaled) > 3:
            y_span = max(b[3] for b in scaled) - min(b[1] for b in scaled)
            y_cover = y_span / max(ph, 1.0)
            if y_cover < 0.35 and scale_mode.startswith("norm"):
                logger.warning(
                    "HPD 第 %s 页 y 覆盖率偏低 %.2f mode=%s，改用像素映射",
                    i + 1,
                    y_cover,
                    scale_mode,
                )
                sx, sy = pw / max(pix.width, 1), ph / max(pix.height, 1)
                scale_mode = "pixel-cover-fallback"
                scaled = _apply_scale(sx, sy)

        fitted = _expand_boxes(scaled, font, ph)
        fontname = _cjk_fontname(page)
        page_debug: list[dict] = []
        for x0, y0, x1, y1, text, fs, expanded in fitted:
            if fs <= _FS_FLOOR + 0.05:
                floor_hits += 1
            # 确保 insert_textbox 真正写入（rc<0 表示一字未写）
            placed = False
            used_fs = fs
            used_box = pymupdf.Rect(x0, y0, x1, y1)
            for _attempt in range(8):
                try:
                    rc = page.insert_textbox(
                        used_box,
                        text,
                        fontname=fontname,
                        fontsize=used_fs,
                        render_mode=3,
                        overlay=True,
                    )
                except Exception as exc:
                    logger.warning("HPD insert_textbox 异常: %s", exc)
                    break
                if rc >= 0:
                    placed = True
                    written += 1
                    break
                # 先向下扩盒，再降字号
                room = min(ph - _EXPAND_GAP, used_box.y1 + abs(rc) + used_fs)
                if room > used_box.y1 + 0.5:
                    used_box = pymupdf.Rect(used_box.x0, used_box.y0, used_box.x1, room)
                    expanded = True
                    continue
                if used_fs > _FS_FLOOR:
                    used_fs = max(_FS_FLOOR, used_fs * 0.85)
                    continue
                logger.warning(
                    "HPD insert_textbox 仍溢出 rc=%s chars=%s fs=%.2f box=%.1fx%.1f",
                    rc,
                    len(text),
                    used_fs,
                    used_box.width,
                    used_box.height,
                )
                break
            if debug:
                page_debug.append(
                    {
                        "text_len": len(text),
                        "text_preview": text[:80],
                        "box": [
                            round(used_box.x0, 2),
                            round(used_box.y0, 2),
                            round(used_box.x1, 2),
                            round(used_box.y1, 2),
                        ],
                        "fontsize": round(used_fs, 2),
                        "expanded": expanded,
                        "placed": placed,
                    }
                )
        if debug:
            y_cover = 0.0
            if fitted:
                y_span = max(b[3] for b in fitted) - min(b[1] for b in fitted)
                y_cover = y_span / max(ph, 1.0)
            debug_pages.append(
                {
                    "page": i + 1,
                    "pix": [pix.width, pix.height],
                    "page_size": [round(pw, 2), round(ph, 2)],
                    "scale_mode": scale_mode,
                    "sx_sy": [round(sx, 5), round(sy, 5)],
                    "raw_max_xy": [max_x, max_y],
                    "y_cover": round(y_cover, 4),
                    "blocks": len(fitted),
                    "items": page_debug,
                }
            )
        logger.info("HPD 第 %s 页 %s 块 mode=%s", i + 1, len(fitted), scale_mode)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)
    doc.close()
    if debug:
        dbg = dest.with_suffix(dest.suffix + ".hpd-debug.json")
        dbg.write_text(
            json.dumps(
                {"src": str(src), "dest": str(dest), "floor_hits": floor_hits, "pages": debug_pages},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        logger.info("HPD debug → %s floor_hits=%s", dbg, floor_hits)
    if written == 0:
        raise RuntimeError("HPD 未识别到文字")
    return dest

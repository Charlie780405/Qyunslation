# SPDX-License-Identifier: MPL-2.0
"""拍照/扫描 PDF → 泰州 HPD 铺不可见文字层。供 pdf2zh 进程直接 import。"""
from __future__ import annotations

import base64
import json
import logging
import math
import os
import re
import sys
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
_COL_X_TOL = 8.0
_SENTENCE_END_RE = re.compile(r"[.!?:;。！？：；」）)\]》]$")
_HARD_END_RE = re.compile(r"[.!。！？][\"'”’)]*$")
_STANDALONE_RE = re.compile(
    r"^(dear|sincerely|enclosure|enclosures|attention|pind|reference\s+id)\b",
    re.I,
)


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


def _cluster_columns(
    boxes: list[tuple[float, float, float, float, str]],
    tol: float = _COL_X_TOL,
) -> list[list[tuple[float, float, float, float, str]]]:
    """按 x0 做 1D 聚类，识别独立列。"""
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda b: (b[0], b[1]))
    cols: list[list[tuple[float, float, float, float, str]]] = []
    centers: list[float] = []
    for box in ordered:
        x0 = box[0]
        placed = False
        for i, cx in enumerate(centers):
            if abs(x0 - cx) <= tol:
                cols[i].append(box)
                # 更新中心为均值
                n = len(cols[i])
                centers[i] = (cx * (n - 1) + x0) / n
                placed = True
                break
        if not placed:
            cols.append([box])
            centers.append(x0)
    return cols


def _should_merge_lines(
    prev: tuple[float, float, float, float, str],
    cur: tuple[float, float, float, float, str],
    *,
    col_width: float,
    aggressive: bool,
) -> bool:
    """同列两行是否应合并为同一段。"""
    _px0, py0, px1, py1, ptext = prev
    _cx0, cy0, _cx1, cy1, _ctext = cur
    prev_h = max(py1 - py0, 1.0)
    gap = cy0 - py1
    # 独立块保护：上下 gap 过大不合并
    if gap > 1.5 * prev_h:
        return False
    # 纵向连续候选
    if gap > 0.6 * prev_h:
        return False
    pstrip = ptext.strip()
    nstrip = _ctext.strip()
    if _STANDALONE_RE.match(pstrip) or _STANDALONE_RE.match(nstrip):
        return False
    ends = bool(_HARD_END_RE.search(pstrip))
    nxt0 = nstrip[:1]
    if ends:
        if not aggressive:
            return False
        # 仅当下一行小写续写（are / enclosed）才跨句号合并
        return bool(nxt0) and nxt0.islower()
    if not aggressive and len(pstrip) < 24:
        return False
    return True


def _merge_lines_into_paragraphs(
    boxes: list[tuple[float, float, float, float, str]],
    *,
    aggressive: bool = True,
) -> list[tuple[float, float, float, float, str]]:
    """行级 box → 段落级 box（列聚类 + 行距 + 句末语义）。"""
    if len(boxes) <= 1:
        return list(boxes)
    merged: list[tuple[float, float, float, float, str]] = []
    for col in _cluster_columns(boxes):
        col_sorted = sorted(col, key=lambda b: (b[1], b[0]))
        col_width = max((b[2] - b[0] for b in col_sorted), default=8.0)
        # 用列内 x 跨度作列宽更稳
        col_x0 = min(b[0] for b in col_sorted)
        col_x1 = max(b[2] for b in col_sorted)
        col_width = max(col_width, col_x1 - col_x0, 8.0)

        cur = col_sorted[0]
        last = col_sorted[0]
        for nxt in col_sorted[1:]:
            # 行距用「上一物理行」而不是已合并并集，避免段高变大后吞掉下一段
            if _should_merge_lines(last, nxt, col_width=col_width, aggressive=aggressive):
                x0 = min(cur[0], nxt[0])
                y0 = min(cur[1], nxt[1])
                x1 = max(cur[2], nxt[2])
                y1 = max(cur[3], nxt[3])
                text = f"{cur[4].rstrip()} {nxt[4].lstrip()}".strip()
                text = " ".join(text.split())
                cur = (x0, y0, x1, y1, text)
                last = nxt
            else:
                merged.append(cur)
                cur = last = nxt
        merged.append(cur)
    merged.sort(key=lambda b: (b[1], b[0]))
    return merged



def _x_overlap_ratio(
    a: tuple[float, float, float, float, str],
    b: tuple[float, float, float, float, str],
) -> float:
    """横向重叠占 a 宽度的比例。"""
    aw = max(a[2] - a[0], 1e-6)
    overlap = min(a[2], b[2]) - max(a[0], b[0])
    return overlap / aw


def _deoverlap_boxes(
    boxes: list[tuple[float, float, float, float, str]],
    *,
    gap: float = _EXPAND_GAP,
    min_h: float = 10.0,
    x_overlap: float = 0.3,
    skip: list[bool] | None = None,
) -> tuple[list[tuple[float, float, float, float, str]], list[bool]]:
    """把每个盒的 y1 压到「所有横向重叠后继盒」的最小 y0 之上。返回 (boxes, clamped)。"""
    if len(boxes) <= 1:
        return list(boxes), [False] * len(boxes)
    ordered = sorted(range(len(boxes)), key=lambda i: (boxes[i][1], boxes[i][0]))
    out = [list(b) for b in boxes]
    clamped = [False] * len(boxes)
    for pos, i in enumerate(ordered):
        if skip and i < len(skip) and skip[i]:
            continue
        x0, y0, x1, y1, text = out[i]
        box_w = max(x1 - x0, 1e-6)
        limit = None
        for j in ordered[pos + 1 :]:
            bx0, by0, bx1, by1, _ = out[j]
            if by0 <= y0:
                continue
            overlap = min(x1, bx1) - max(x0, bx0)
            if overlap > x_overlap * box_w:
                limit = by0 if limit is None else min(limit, by0)
        if limit is None:
            continue
        new_y1 = min(y1, limit - gap)
        floor = y0 + min_h
        if new_y1 < floor:
            logger.warning(
                "HPD 去重叠触 min_h: chars=%s y0=%.1f y1=%.1f→%.1f limit=%.1f",
                len(text),
                y0,
                y1,
                floor,
                limit,
            )
            new_y1 = floor
        if new_y1 < y1 - 0.05:
            clamped[i] = True
            out[i] = [x0, y0, x1, new_y1, text]
    result = [(b[0], b[1], b[2], b[3], b[4]) for b in out]
    return result, clamped


def _expand_boxes(
    boxes: list[tuple[float, float, float, float, str]],
    font,
    page_h: float,
    *,
    fs_floor: float = _FS_FLOOR,
    roles: list[str] | None = None,
    x_overlap: float = 0.3,
) -> list[tuple[float, float, float, float, str, float, bool]]:
    """盒高不足时向下扩展（受下一块 y1 限制），再求字号。"""
    ordered = sorted(enumerate(boxes), key=lambda it: (it[1][1], it[1][0]))
    out: list[tuple[float, float, float, float, str, float, bool] | None] = [None] * len(boxes)
    for idx, (orig_i, (x0, y0, x1, y1, text)) in enumerate(ordered):
        if roles and orig_i < len(roles) and roles[orig_i] in {"kv", "section"}:
            fs_role = 10.0 if roles[orig_i] == "kv" else 14.0
            out[orig_i] = (x0, y0, x1, y1, text, fs_role, False)
            continue
        box_w = max(x1 - x0, 8.0)
        box_h = max(y1 - y0, 8.0)
        expanded = False
        # 已是段落高盒用 1.05；单行扁盒（高/宽小）仍 1.2，避免字号塌回地板
        expand_factor = 1.05 if box_h >= 28.0 else 1.2
        need = _needed_height(font, text, box_w, fs_floor) * expand_factor
        if need > box_h + 0.5:
            limit = page_h - _EXPAND_GAP
            # 扫所有后继同列盒取最小 y0，避免跳过一个仍撞上第二个
            for j in range(idx + 1, len(ordered)):
                nx0, ny0, nx1, _, _ = ordered[j][1]
                if ny0 <= y0:
                    continue
                overlap = min(x1, nx1) - max(x0, nx0)
                if overlap > box_w * x_overlap:
                    limit = min(limit, ny0 - _EXPAND_GAP)
            new_y1 = min(y0 + need, limit)
            if new_y1 > y1:
                y1 = new_y1
                box_h = max(y1 - y0, 8.0)
                expanded = True
        fs = _fit_fontsize(font, text, box_w, box_h, lo=fs_floor)
        if fs <= fs_floor + 0.05:
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
    aggressive: bool = True,
    min_font_size: float | None = None,
    profile: str | None = None,
    graphics: bool | None = None,
) -> Path:
    import pymupdf

    src = Path(src)
    dest = dest or src.with_name(f"{src.stem}.hpd-ocr.pdf")
    dest = Path(dest)
    enable_graphics = (graphics is True) or (
        graphics is None and (profile or "").strip() == "letter"
    )
    graphics_pages: dict[int, list] = {}
    fs_floor = float(min_font_size) if min_font_size is not None else _FS_FLOOR
    debug = os.environ.get("QYUNSLATION_HPD_DEBUG", "").strip() in {
        "1",
        "true",
        "yes",
    } or (profile or "").strip() == "letter"
    debug_pages: list[dict] = []
    doc = pymupdf.open(src)
    written = 0
    floor_hits = 0
    total = len(doc)
    font = _pymupdf_font()
    try:
        hpd_workers = max(1, int(os.environ.get("QYUNSLATION_HPD_WORKERS", "1") or "1"))
    except ValueError:
        hpd_workers = 1

    # 预取：串行渲染 pixmap（pymupdf 线程不安全），并行打 HPD /parse
    # 实测 HPD 同卡串行更快，默认 workers=1；多卡/升级后再调 QYUNSLATION_HPD_WORKERS
    page_raws: list[str | None] = [None] * total
    page_pix: list = [None] * total
    page_err: list[BaseException | None] = [None] * total

    def _render(i: int):
        page = doc[i]
        pix = page.get_pixmap(dpi=dpi)
        b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode()
        return i, pix, b64

    rendered = [_render(i) for i in range(total)]
    for i, pix, _b64 in rendered:
        page_pix[i] = pix

    def _parse_one(item):
        i, pix, b64 = item
        try:
            return i, _parse(HPD_URL, b64), None
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            return i, None, exc

    if hpd_workers <= 1:
        parsed = []
        for item in rendered:
            r = _parse_one(item)
            parsed.append(r)
            if progress_cb:
                progress_cb(r[0] + 1, total)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        parsed = [None] * total
        with ThreadPoolExecutor(max_workers=hpd_workers) as ex:
            futs = {ex.submit(_parse_one, item): item[0] for item in rendered}
            done_n = 0
            for fut in as_completed(futs):
                i, raw, err = fut.result()
                parsed[i] = (i, raw, err)
                done_n += 1
                if progress_cb:
                    progress_cb(done_n, total)
    for i, raw, err in parsed:
        page_raws[i] = raw
        page_err[i] = err

    for i, page in enumerate(doc):
        if progress_cb:
            progress_cb(i + 1, total)
        pix = page_pix[i]
        if page_err[i] is not None:
            logger.warning("HPD 第 %s 页失败: %s", i + 1, page_err[i])
            continue
        raw = page_raws[i]
        if not raw:
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

        n_lines = len(scaled)
        letter_roles: list[str] = []
        clamped_flags: list[bool] = []
        is_letter = (profile or "").strip() == "letter"

        if is_letter:
            try:
                from letter_layout import (
                    clean_text,
                    fold_short_titles,
                    group_for_merge,
                    clamp_before_section_heads,
                    pack_kv_table,
                    split_kv_rows,
                    split_named_sections,
                    split_leading_caps_title,
                    tag_blocks,
                )
            except ImportError:
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from letter_layout import (  # type: ignore
                    clean_text,
                    fold_short_titles,
                    group_for_merge,
                    clamp_before_section_heads,
                    pack_kv_table,
                    split_kv_rows,
                    split_named_sections,
                    split_leading_caps_title,
                    tag_blocks,
                )

            # 1) 逐行清洗
            cleaned: list[tuple[float, float, float, float, str]] = []
            for x0, y0, x1, y1, raw_t in scaled:
                ct = clean_text(raw_t)
                if ct:
                    cleaned.append((x0, y0, x1, y1, ct))
            cleaned = split_kv_rows(cleaned, pw)
            cleaned = split_named_sections(cleaned)
            cleaned = split_leading_caps_title(cleaned)
            # 图形擦除必须用排版前原始盒；pack/clamp 会改写 y（可差 ~58pt）
            raw_boxes = [b[:4] for b in cleaned]
            cleaned = pack_kv_table(cleaned, pw, ph)
            cleaned = clamp_before_section_heads(cleaned)
            # 2) 行级角色 + 眼科并入职务行
            roles = tag_blocks(cleaned, pw, ph)
            cleaned, roles = fold_short_titles(cleaned, roles)
            # 2b) 图形区检测 + 丢弃 logo/印章区内的行（须在 merge/deoverlap 前）
            if enable_graphics:
                try:
                    from graphic_regions import detect as _gr_detect, drop_boxes_in_suppress
                except ImportError:
                    import sys as _sys
                    _sys.path.insert(0, str(Path(__file__).resolve().parent))
                    from graphic_regions import (  # type: ignore
                        detect as _gr_detect,
                        drop_boxes_in_suppress,
                    )
                erase_boxes = list(raw_boxes) + [b[:4] for b in cleaned]
                regs = _gr_detect(page, erase_boxes)
                if regs:
                    before = len(cleaned)
                    cleaned = drop_boxes_in_suppress(cleaned, regs)
                    roles = tag_blocks(cleaned, pw, ph)
                    cleaned, roles = fold_short_titles(cleaned, roles)
                    graphics_pages[i + 1] = regs
                    logger.info(
                        "HPD 第 %s 页图形区 %s 个，丢行 %s→%s",
                        i + 1,
                        len(regs),
                        before,
                        len(cleaned),
                    )
            # 3) 仅对 MERGE_ROLES 连续行聚合
            out_boxes: list[tuple[float, float, float, float, str]] = []
            out_roles: list[str] = []
            for sub, role, mergeable in group_for_merge(cleaned, roles):
                if mergeable and len(sub) > 1:
                    sub = _merge_lines_into_paragraphs(sub, aggressive=aggressive)
                out_boxes.extend(sub)
                out_roles.extend([role] * len(sub))
            logger.info(
                "HPD 第 %s 页 letter 角色聚合 %s→%s",
                i + 1,
                n_lines,
                len(out_boxes),
            )
            # 4) 去纵向重叠（kv 已 pack 成等高表，不再压扁）
            skip_kv = [r in {"kv", "section"} for r in out_roles]
            scaled, clamped_flags = _deoverlap_boxes(
                out_boxes, gap=0.5, min_h=16.0, x_overlap=0.15, skip=skip_kv
            )
            letter_roles = out_roles
            if any(clamped_flags):
                logger.info(
                    "HPD 第 %s 页去重叠 clamped=%s/%s",
                    i + 1,
                    sum(clamped_flags),
                    len(clamped_flags),
                )
        else:
            scaled = _merge_lines_into_paragraphs(scaled, aggressive=aggressive)
            logger.info(
                "HPD 第 %s 页段落聚合 %s→%s aggressive=%s",
                i + 1,
                n_lines,
                len(scaled),
                aggressive,
            )
            clamped_flags = [False] * len(scaled)

        fitted = _expand_boxes(
            scaled,
            font,
            ph,
            fs_floor=fs_floor,
            roles=letter_roles or None,
            x_overlap=0.15 if is_letter else 0.3,
        )
        if is_letter:
            boxes_only = [(a, b, c, d, e) for a, b, c, d, e, _fs, _ex in fitted]
            boxes_only = clamp_before_section_heads(boxes_only)
            fitted = [
                (nb[0], nb[1], nb[2], nb[3], nb[4], fitted[i][5], fitted[i][6])
                for i, nb in enumerate(boxes_only)
            ]
        fontname = _cjk_fontname(page)
        page_debug: list[dict] = []
        # insert 扩盒不得越过后继同列盒（否则 debug/BabelDOC 又纵向重叠）
        _fit_boxes = [(b[0], b[1], b[2], b[3]) for b in fitted]
        for idx_fit, (x0, y0, x1, y1, text, fs, expanded) in enumerate(fitted):
            if fs <= fs_floor + 0.05:
                floor_hits += 1
            insert_limit = ph - _EXPAND_GAP
            box_w = max(x1 - x0, 1e-6)
            for j, (nx0, ny0, nx1, ny1) in enumerate(_fit_boxes):
                if j == idx_fit or ny0 <= y0:
                    continue
                overlap = min(x1, nx1) - max(x0, nx0)
                if overlap > box_w * (0.15 if is_letter else 0.3):
                    insert_limit = min(insert_limit, ny0 - _EXPAND_GAP)
            # 确保 insert_textbox 真正写入（rc<0 表示一字未写）
            placed = False
            role = letter_roles[idx_fit] if idx_fit < len(letter_roles) else None
            used_fs = 10.0 if role == "kv" else (14.0 if role == "section" else fs)
            used_box = pymupdf.Rect(x0, y0, min(x1, x0 + box_w), min(y1, max(y0 + 10.0, insert_limit)))
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
                # 先向下扩盒（受后继盒限制），再降字号
                room = min(insert_limit, used_box.y1 + abs(rc) + used_fs)
                if room > used_box.y1 + 0.5:
                    used_box = pymupdf.Rect(used_box.x0, used_box.y0, used_box.x1, room)
                    expanded = True
                    continue
                if role in {"kv", "section"}:
                    break
                if used_fs > 4.0:
                    # OCR 不可见层可继续降字号，优先保证写入
                    used_fs = max(4.0, used_fs * 0.85)
                    continue
                logger.warning(
                    "HPD insert_textbox 仍溢出 rc=%s chars=%s fs=%.2f box=%.1fx%.1f，改点插入",
                    rc,
                    len(text),
                    used_fs,
                    used_box.width,
                    used_box.height,
                )
                try:
                    fs_fb = max(4.0, min(used_fs, max(used_box.height * 0.8, 4.0)))
                    page.insert_text(
                        (used_box.x0, min(used_box.y1 - 0.5, used_box.y0 + fs_fb)),
                        text,
                        fontname=fontname,
                        fontsize=fs_fb,
                        render_mode=3,
                        overlay=True,
                    )
                    placed = True
                    written += 1
                    used_fs = fs_fb
                except Exception as exc2:
                    logger.warning("HPD insert_text 兜底失败: %s", exc2)
                break
            if debug:
                page_debug.append(
                    {
                        "text_len": len(text),
                        "text": text,
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
                        "clamped": clamped_flags[idx_fit] if idx_fit < len(clamped_flags) else False,
                        "y1_before": round(y1, 2),
                        "role": letter_roles[idx_fit] if idx_fit < len(letter_roles) else None,
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
                    "lines_before_merge": n_lines,
                    "aggressive": aggressive,
                    "profile": profile,
                    "items": page_debug,
                }
            )
        logger.info("HPD 第 %s 页 %s 块 mode=%s", i + 1, len(fitted), scale_mode)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)
    doc.close()
    if enable_graphics and graphics_pages:
        try:
            from graphic_regions import write_manifest as _gr_write
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
            from graphic_regions import write_manifest as _gr_write  # type: ignore
        try:
            _gr_write(dest, src, graphics_pages)
        except Exception as exc:
            logger.warning("graphics manifest 写入失败: %s", exc)
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

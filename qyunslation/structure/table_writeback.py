# SPDX-License-Identifier: MPL-2.0
"""PLAN-033j：把已译表格块写回 PDF（矢量网格 + 可搜索文字 + 续页）。"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from .models import BoundingBox, TranslatableBlock
from .role_fitter import (
    QC_FONT_BELOW_TARGET,
    QC_OVERFLOW,
    QC_ROLE_SIZE_DRIFT,
    FitBlock,
    FitResult,
    measure_textbox,
    table_hard_fail_codes,
)
from .cjk_font import resolve_static_cjk
from .table_cell_policy import has_script_runs, split_script_runs
from .table_translate import (
    CONTINUATION_LABEL,
    TableTranslateError,
    plan_dual_continuations,
)

# 可变/Thin 字体（.env 里的 NotoSansSC.ttf）会让汉字比数字淡一截，统一换静态字面。
CJK_REGULAR = resolve_static_cjk(
    os.environ.get("QYUNSLATION_FONT", "/home/dev/.fonts/NotoSansSC-Regular.otf")
)
CJK_BOLD = resolve_static_cjk(
    os.environ.get("QYUNSLATION_FONT_BOLD", "/home/dev/.fonts/NotoSansSC-Bold.otf"), bold=True
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_FONT_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
_PAGE_FONTS: dict[int, tuple[str, str]] = {}
_EMBED_NAME = "qcjk"
_CJK_MEASURE = None
_ACTIVE_FONT: tuple[str, Path, frozenset[str]] | None = None  # (内嵌名, 子集文件, 字符集)
_SUBSET_DIR = Path(os.environ.get("QYUNSLATION_FONT_SUBSET_DIR", "/tmp/qyunslation-font-subsets"))
_BASE_CHARS = "".join(chr(c) for c in range(0x20, 0x7F)) + "，。、；：？！（）【】《》“”‘’…—·％≥≤±×μ°"


def _cjk_font():
    """CJK 量字宽字体：与内嵌字体同一份，缺文件才回退 china-ss。"""
    import pymupdf

    global _CJK_MEASURE
    if _CJK_MEASURE is None:
        try:
            _CJK_MEASURE = (
                pymupdf.Font(fontfile=str(CJK_REGULAR))
                if CJK_REGULAR.is_file()
                else pymupdf.Font("china-ss")
            )
        except Exception:
            _CJK_MEASURE = pymupdf.Font("china-ss")
    return _CJK_MEASURE


def _subset_font(chars: frozenset[str]) -> tuple[str, Path, frozenset[str]] | None:
    """按字符集生成（并按内容缓存）Noto 子集；fontTools 不可用或失败返回 None。"""
    if not CJK_REGULAR.is_file():
        return None
    ordered = "".join(sorted(chars))
    digest = hashlib.sha1(ordered.encode("utf-8")).hexdigest()[:10]
    target = _SUBSET_DIR / f"NotoSansSC-Regular-{digest}.otf"
    try:
        if not target.is_file():
            from fontTools import subset

            _SUBSET_DIR.mkdir(parents=True, exist_ok=True)
            opts = subset.Options()
            opts.layout_features = []
            opts.notdef_outline = True
            opts.name_IDs = [1, 2]
            font = subset.load_font(str(CJK_REGULAR), opts)
            sub = subset.Subsetter(opts)
            sub.populate(text=ordered)
            sub.subset(font)
            tmp = target.with_suffix(".tmp")
            subset.save_font(font, str(tmp), opts)
            tmp.replace(target)
        return f"{_EMBED_NAME}{digest}", target, chars
    except Exception:
        return None


def prepare_embedded_font(texts) -> None:
    """按本表实际用字准备子集 Noto（数十 KB）；之后 _page_font 命中即复用。"""
    global _ACTIVE_FONT
    chars = frozenset(_BASE_CHARS) | frozenset(
        ch for t in texts for ch in (t or "") if not ch.isspace()
    )
    _ACTIVE_FONT = _subset_font(chars)


def _page_font(page, fname: str, text: str = "") -> str:
    """china-ss 不内嵌，浏览器查看器画不出中文；改用内嵌 Noto 子集并在本页登记。

    全字库提取文字时会把「不」等映射成兼容字，所以只用子集；子集缺字时临时补一个小子集。
    """
    if fname != "china-ss" or not CJK_REGULAR.is_file():
        return fname
    need = frozenset(ch for ch in (text or "") if not ch.isspace())
    chosen = _ACTIVE_FONT if _ACTIVE_FONT and need <= _ACTIVE_FONT[2] else None
    if chosen is None:
        chosen = _subset_font(need | {" "})
    if chosen is not None:
        name, path, _chars = chosen
    else:
        name, path = _EMBED_NAME, CJK_REGULAR
    # 以页面实际字体表为准（按 id 缓存会在文档对象复用地址时漏登记）
    if not any(f[4] == name for f in page.get_fonts()):
        page.insert_font(fontname=name, fontfile=str(path))
    return name


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _paint_font(text: str, *, bold: bool):
    import pymupdf

    if _has_cjk(text) or not all(_helv_has(ch) for ch in text or ""):
        return "china-ss", _cjk_font()
    return ("hebo" if bold else "helv"), pymupdf.Font("helv")


def _latin_name(bold: bool) -> str:
    return "hebo" if bold else "helv"


def _helv_has(ch: str) -> bool:
    """内置 Helvetica 落笔只可靠支持 Latin-1；≥、–（en dash）、’ 等须交给 CJK 字体，否则画成「·」或「?」。"""
    return ord(ch) < 256


def _script_runs(text: str, *, bold: bool) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    buf: list[str] = []
    cjk: bool | None = None
    for ch in text:
        now = bool(_CJK_FONT_RE.match(ch)) or not _helv_has(ch)
        if cjk is None:
            cjk = now
        elif now != cjk:
            runs.append(("china-ss" if cjk else _latin_name(bold), "".join(buf)))
            buf = []
            cjk = now
        buf.append(ch)
    if buf:
        runs.append(("china-ss" if cjk else _latin_name(bold), "".join(buf)))
    return runs


def output_bbox(
    bbox: BoundingBox,
    page_width: float,
    *,
    x_min_frac: float | None,
) -> BoundingBox:
    dx = float(page_width) * float(x_min_frac) if x_min_frac else 0.0
    return BoundingBox(
        x0=bbox.x0 + dx,
        y0=bbox.y0,
        x1=bbox.x1 + dx,
        y1=bbox.y1,
    )


def _ensure_fonts(page) -> tuple[str, str]:
    """西文用内置 Helvetica，避免 china-ss 把拉丁字母拉成全角间距。"""
    key = id(page)
    cached = _PAGE_FONTS.get(key)
    if cached:
        return cached
    names = ("helv", "hebo")
    _PAGE_FONTS[key] = names
    return names


def redact_source_blocks(
    page,
    blocks: list[TranslatableBlock],
    *,
    x_min_frac: float | None,
    pad: float = 1.2,
) -> int:
    """Permanently remove source text while preserving table graphics.

    PLAN-042d：对单元格 bbox 做小幅膨胀，覆盖多行源 span / 描边残留。
    """
    import pymupdf

    width = float(page.rect.width)
    seen: set[tuple[float, float, float, float]] = set()
    for block in blocks:
        if not block.bbox or not (block.source_text or "").strip():
            continue
        bbox = output_bbox(block.bbox, width, x_min_frac=x_min_frac)
        key = (
            round(bbox.x0 - pad, 3),
            round(bbox.y0 - pad, 3),
            round(bbox.x1 + pad, 3),
            round(bbox.y1 + pad, 3),
        )
        if key in seen:
            continue
        seen.add(key)
        rect = pymupdf.Rect(*key)
        # clamp to page
        rect = rect & page.rect
        if rect.is_empty or rect.width < 1 or rect.height < 1:
            raise TableTranslateError(f"TABLE_CELL_BOX_INVALID:{block.block_id}")
        page.add_redact_annot(rect, fill=False, cross_out=False)
    if seen:
        page.apply_redactions(images=0, graphics=0, text=0)
    return len(seen)


def union_paint_bbox(bbox, blocks):
    """题注常高出 table region；擦除须覆盖全部将落笔的块，否则双标题。"""
    xs: list[float] = []
    ys: list[float] = []
    if bbox is not None:
        if hasattr(bbox, "x0"):
            xs.extend([float(bbox.x0), float(bbox.x1)])
            ys.extend([float(bbox.y0), float(bbox.y1)])
        else:
            xs.extend([float(bbox[0]), float(bbox[2])])
            ys.extend([float(bbox[1]), float(bbox[3])])
    for block in blocks or []:
        box = getattr(block, "bbox", None)
        if box is None:
            continue
        xs.extend([float(box.x0), float(box.x1)])
        ys.extend([float(box.y0), float(box.y1)])
    if not xs:
        return bbox
    return BoundingBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


def redact_table_region(
    page,
    bbox,
    *,
    x_min_frac: float | None,
    pad: float = 2.0,
) -> bool:
    """PLAN-048：整区擦除译文页上 BabelDOC 已重排的表文，保留框线。

    按原文墨迹格擦会漏掉重排段落，再落笔就是双渲染器乱套。
    """
    import pymupdf

    if bbox is None:
        return False
    width = float(page.rect.width)
    if hasattr(bbox, "x0"):
        box = output_bbox(bbox, width, x_min_frac=x_min_frac)
        x0, y0, x1, y1 = box.x0, box.y0, box.x1, box.y1
    else:
        x0, y0, x1, y1 = (float(v) for v in bbox[:4])
        if x_min_frac:
            dx = width * float(x_min_frac)
            x0, x1 = x0 + dx, x1 + dx
    rect = pymupdf.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & page.rect
    # PLAN-084: the 2pt top pad used to clip the caption line sitting just above the table (its glyph boxes dip
    # below the table's top edge), and redaction removes every glyph it touches — the table title vanished.
    try:
        top = rect.y0
        probe = pymupdf.Rect(rect.x0, rect.y0 - 24.0, rect.x1, rect.y0 + 4.0)
        for word in page.get_text("words", clip=probe):
            if (float(word[1]) + float(word[3])) / 2.0 < y0 and float(word[3]) > rect.y0:
                top = max(top, float(word[3]) + 0.05)
        rect.y0 = min(top, max(rect.y0, y0))
    except Exception:
        pass
    if rect.is_empty or rect.width < 4 or rect.height < 4:
        return False
    page.add_redact_annot(rect, fill=False, cross_out=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    return True


_FILLS: list[tuple[tuple[float, float, float, float], tuple[float, float, float]]] = []
_INK: tuple[float, float, float] = (0.0, 0.0, 0.0)
_SCRIPT_SCALE = 0.7
_SUB_DROP = 0.22
_SUP_RISE = 0.38


def snapshot_fills(page) -> None:
    """落笔前记下本页的填充矩形（表头深色底、隔行浅灰底）；落笔后再取会读到我们自己画的白底。"""
    global _FILLS
    _FILLS = []
    try:
        page_area = float(page.rect.width) * float(page.rect.height)
        for item in page.get_drawings():
            fill = item.get("fill")
            if not fill or len(fill) < 3:
                continue
            if float(item.get("fill_opacity", 1.0) or 1.0) < 0.5:
                continue
            rect = item.get("rect")
            if rect is None or rect.is_empty:
                continue
            if rect.width * rect.height > 0.9 * page_area:
                continue
            _FILLS.append(((rect.x0, rect.y0, rect.x1, rect.y1), (float(fill[0]), float(fill[1]), float(fill[2]))))
    except Exception:
        _FILLS = []


def _cell_fill(rect) -> tuple[float, float, float]:
    """格子中心下面最上层的填充色；没有就是白底。"""
    cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
    for (x0, y0, x1, y1), color in reversed(_FILLS):
        if x0 - 0.5 <= cx <= x1 + 0.5 and y0 - 0.5 <= cy <= y1 + 0.5:
            return color
    return (1.0, 1.0, 1.0)


def _ink_for(fill: tuple[float, float, float]) -> tuple[float, float, float]:
    lum = 0.299 * fill[0] + 0.587 * fill[1] + 0.114 * fill[2]
    return (1.0, 1.0, 1.0) if lum < 0.5 else (0.0, 0.0, 0.0)


def _wrap_to_width(text: str, *, font, font_size: float, width: float) -> list[str]:
    """西文整词换行；含汉字按字宽断行，避免窄格整句画不出。"""
    raw = (text or "").replace("\xa0", " ").strip()
    if not raw:
        return [""]
    if _has_cjk(raw):
        lines: list[str] = []
        current = ""
        for ch in raw:
            trial = current + ch
            if current and float(font.text_length(trial, fontsize=font_size)) > width:
                lines.append(current)
                current = ch.strip() or ch
            else:
                current = trial
        if current:
            lines.append(current)
        return lines or [""]
    words = raw.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if float(font.text_length(trial, fontsize=font_size)) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def paint_cell(
    page,
    bbox: BoundingBox,
    text: str,
    *,
    bold: bool,
    font_size: float,
    role: str = "table_cell",
) -> float:
    import pymupdf

    rect = pymupdf.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    if rect.is_empty or rect.width < 2 or rect.height < 2:
        raise TableTranslateError("TABLE_CELL_BOX_INVALID")
    # 短格略收 inset，保证 7pt 两行（如 Healthy Subjects）不压底线
    short = rect.height < 20
    inset_x = 0.6 if short else 1.6
    inset_y = 0.25 if short else 1.0
    if "footnote" in (role or "").lower():
        inset_y = min(inset_y, 0.7)
    inset = pymupdf.Rect(
        rect.x0 + inset_x,
        rect.y0 + inset_y,
        rect.x1 - inset_x,
        rect.y1 - inset_y,
    )
    if inset.is_empty or inset.width < 1 or inset.height < 1:
        inset = pymupdf.Rect(rect.x0 + 0.8, rect.y0 + 0.5, rect.x1 - 0.8, rect.y1 - 0.5)
    if inset.is_empty:
        inset = rect
    fontname, measure_font = _paint_font(text, bold=bold)
    size = max(6.0, float(font_size))
    # 仅真竖排轴标签旋转；数字窄格（IGA=1）旋转会把整表拧碎
    if inset.width < 8.0 and inset.height >= 40.0:
        return _paint_cell_sideways(page, inset, text, fontname=fontname, font_size=size)
    global _INK
    fill = _cell_fill(inset)
    _INK = _ink_for(fill)
    page.draw_rect(inset, color=fill, fill=fill, width=0)
    # 期刊表体行高常 <11pt：textbox 在 6pt 仍 rc<0 会“成功”却不落字
    if short:
        return _paint_short_line(
            page, inset, text, bold=bold, font_size=size, fontname=fontname, measure_font=measure_font
        )
    mixed = (_has_cjk(text) and re.search(r"[A-Za-z]", text or "")) or has_script_runs(text)
    if mixed:
        return _paint_mixed(page, inset, text, bold=bold, font_size=size)
    while True:
        lines = _wrap_to_width(text, font=measure_font, font_size=size, width=inset.width)
        need_h = max(len(lines), 1) * size * 1.2
        if need_h <= inset.height + 0.3 or size <= 6.0:
            rc = page.insert_textbox(
                inset,
                "\n".join(lines),
                fontname=_page_font(page, fontname, "\n".join(lines)),
                fontsize=size,
                align=0,
                color=_INK,
            )
            if rc >= 0:
                return size
            if size <= 6.0:
                # insert_textbox draws nothing when the text misses the box by a hair; never leave a header cell blank
                # (PLAN-084: 「MG-K10 300 mg Q4W (n=41)」整格消失)。
                _draw_lines_anyway(page, inset, lines, fontname=fontname, font_size=size)
                return size
        size = max(6.0, size - 0.5)


def _draw_lines_anyway(page, inset, lines: list[str], *, fontname: str, font_size: float) -> None:
    text = "\n".join(lines)
    name = _page_font(page, fontname, text)
    y = inset.y0 + font_size * 0.95
    for line in lines:
        if line:
            page.insert_text((inset.x0, y), line, fontname=name, fontsize=font_size, color=_INK)
        y += font_size * 1.12


def _paint_short_line(
    page,
    inset,
    text: str,
    *,
    bold: bool,
    font_size: float,
    fontname: str,
    measure_font,
) -> float:
    """单行落字：矮格用 insert_text，避免 textbox rc<0 却当成功。"""
    if (_has_cjk(text) and re.search(r"[A-Za-z]", text or "")) or has_script_runs(text):
        return _paint_mixed(page, inset, text, bold=bold, font_size=min(font_size, inset.height))
    size = min(float(font_size), max(4.5, float(inset.height) * 0.92))
    while size > 4.5 and float(measure_font.text_length(text, fontsize=size)) > inset.width:
        size -= 0.25
    # PyMuPDF's text bbox extends above the insertion baseline by the font
    # ascent. The old 0.88 multiplier placed the visible glyph outside the
    # cell's top edge for 7pt Latin labels (notably ``Healthy Subjects``).
    # Keep a small bottom guard while positioning against the actual ascent.
    y = min(inset.y0 + size * 1.08, inset.y1 - size * 0.18)
    page.insert_text((inset.x0, y), text, fontname=_page_font(page, fontname, text), fontsize=size, color=_INK)
    return size


def _paint_mixed(page, inset, text: str, *, bold: bool, font_size: float) -> float:
    """中英混排落笔；角标（下标/上标）用小字号并偏移基线。"""
    import pymupdf

    fonts = {
        "helv": pymupdf.Font("helv"),
        "hebo": pymupdf.Font("helv"),
        "china-ss": _cjk_font(),
    }
    size = max(6.0, float(font_size))
    leading = 1.15
    parts = split_script_runs(text)
    while True:
        # line 元素：(字体, 片段, 角标种类)；宽度按该片段自己的字号算
        lines: list[list[tuple[str, str, str]]] = [[]]
        line_w = 0.0
        for part, kind in parts:
            scale = _SCRIPT_SCALE if kind else 1.0
            psize = size * scale
            for fname, chunk in _script_runs(part, bold=bold):
                font = fonts[fname]
                pieces = list(chunk) if fname == "china-ss" else (chunk.split(" ") if chunk.strip() else [chunk])
                for i, piece in enumerate(pieces):
                    if fname != "china-ss" and i and piece:
                        piece = " " + piece
                    w = float(font.text_length(piece, fontsize=psize)) if piece else 0.0
                    # 角标紧贴基名，不在它前面换行
                    if lines[-1] and not kind and line_w + w > inset.width and piece.strip():
                        lines.append([])
                        line_w = 0.0
                        piece = piece.lstrip()
                        w = float(font.text_length(piece, fontsize=psize)) if piece else 0.0
                    if not piece:
                        continue
                    if lines[-1] and lines[-1][-1][0] == fname and lines[-1][-1][2] == kind:
                        lines[-1][-1] = (fname, lines[-1][-1][1] + piece, kind)
                    else:
                        lines[-1].append((fname, piece, kind))
                    line_w += w
        need_h = max(len(lines), 1) * size * leading
        if need_h <= inset.height + 0.3 or size <= 6.0:
            y = inset.y0 + size * 0.95
            for line in lines:
                if y > inset.y1 - 0.2:
                    break
                x = inset.x0
                for fname, chunk, kind in line:
                    psize = size * (_SCRIPT_SCALE if kind else 1.0)
                    dy = size * _SUB_DROP if kind == "sub" else (-size * _SUP_RISE if kind == "sup" else 0.0)
                    page.insert_text(
                        (x, y + dy), chunk, fontname=_page_font(page, fname, chunk), fontsize=psize, color=_INK
                    )
                    x += float(fonts[fname].text_length(chunk, fontsize=psize))
                y += size * leading
            return size
        size = max(6.0, size - 0.5)


def _paint_cell_sideways(page, inset, text: str, *, fontname: str, font_size: float) -> float:
    import pymupdf

    size = max(3.0, float(font_size))
    while True:
        fill = _cell_fill(inset)
        page.draw_rect(inset, color=fill, fill=fill, width=0)
        # 字号需落在短边内；文本长度沿长边。
        fits_width = size <= inset.width * 0.95
        fits_len = len(text) * size * 0.55 <= inset.height
        if (fits_width and fits_len) or size <= 3.0:
            origin = pymupdf.Point(inset.x0 + inset.width * 0.15, inset.y1 - 1.0)
            page.insert_text(
                origin,
                text,
                fontname=_page_font(page, fontname, text),
                fontsize=size,
                rotate=90,
                color=_ink_for(fill),
            )
            return size
        size = max(3.0, size - 0.5)


def blocks_to_fit(blocks: list[TranslatableBlock], translations: dict[str, str]) -> list[FitBlock]:
    fitted = []
    for block in blocks:
        style = block.source_style
        size = float(style.font_size) if style and style.font_size else 9.0
        weight = (style.font_weight if style and style.font_weight else "regular") or "regular"
        box = block.bbox
        box_w = float(box.x1 - box.x0) if box else 80.0
        box_h = float(box.y1 - box.y0) if box else 16.0
        if box_w < 8.0 and box_h >= 40.0:
            box_w, box_h = box_h, box_w
        fitted.append(
            FitBlock(
                block_id=block.block_id,
                role=str(block.role or "table_cell"),
                source_text=block.source_text,
                translated_text=translations[block.block_id],
                source_size=size,
                source_bold=weight not in {"regular", "normal", None},
                box_w=box_w,
                box_h=box_h,
            )
        )
    return fitted


def _is_body_role(role: str) -> bool:
    value = (role or "table_cell").lower()
    return "title" not in value and "header" not in value and "footnote" not in value


def paint_fitted_blocks(
    page,
    blocks: list[TranslatableBlock],
    results: list[FitResult],
    *,
    x_min_frac: float | None,
    allow_leftover: bool = True,
) -> tuple[list[str], str, list[str], list[list[str]]]:
    prepare_embedded_font(r.text for r in results)
    snapshot_fills(page)
    codes: list[str] = []
    width = float(page.rect.width)
    title = ""
    header: list[str] = []
    leftover: list[list[str]] = []
    overflowing = False
    current_row: int | None = None
    row_cells: list[str] = []

    def flush_row() -> None:
        nonlocal current_row, row_cells
        if current_row is not None:
            leftover.append(row_cells)
        current_row = None
        row_cells = []

    paired = sorted(
        zip(blocks, results, strict=True),
        key=lambda item: (item[0].row_index or 0, item[0].column_index or 0),
    )
    for block, result in paired:
        role = str(block.role or "table_cell")
        if "title" in role.lower():
            title = result.text
        elif "header" in role.lower():
            header.append(result.text)
        if allow_leftover and overflowing and _is_body_role(role):
            row = block.row_index if block.row_index is not None else 0
            if current_row != row:
                flush_row()
                current_row = row
            row_cells.append(result.text)
            continue
        # A caller may provide a raw FitResult (for example from a retry or an
        # OCR path) without setting ``overflow``.  Re-check the actual cell
        # geometry before painting so an impossible body cell is continued
        # instead of silently shrinking to an unreadable glyph size.
        if allow_leftover and _is_body_role(role) and block.bbox:
            box_w = max(1.0, float(block.bbox.x1 - block.bbox.x0))
            box_h = max(1.0, float(block.bbox.y1 - block.bbox.y0))
            if result.overflow or QC_OVERFLOW in result.qc or not measure_textbox(
                result.text, result.font_size, box_w, box_h
            ):
                overflowing = True
                row = block.row_index if block.row_index is not None else 0
                if current_row != row:
                    flush_row()
                    current_row = row
                row_cells.append(result.text)
                continue
        codes.extend(result.qc)
        if not block.bbox:
            raise TableTranslateError(f"TABLE_CELL_BOX_MISSING:{block.block_id}")
        try:
            used = paint_cell(
                page,
                output_bbox(block.bbox, width, x_min_frac=x_min_frac),
                result.text,
                bold=result.bold,
                font_size=result.font_size,
                role=role,
            )
            if used + 1e-6 < result.font_size and QC_FONT_BELOW_TARGET not in result.qc:
                result.qc.append(QC_FONT_BELOW_TARGET)
                result.font_size = used
        except TableTranslateError as exc:
            if allow_leftover and "OVERFLOW" in str(exc) and _is_body_role(role):
                overflowing = True
                row = block.row_index if block.row_index is not None else 0
                if current_row != row:
                    flush_row()
                    current_row = row
                row_cells.append(result.text)
                continue
            if not allow_leftover:
                continue
            raise
    if overflowing:
        flush_row()
    hard = [
        code
        for code in table_hard_fail_codes(results)
        if code not in {QC_OVERFLOW, QC_ROLE_SIZE_DRIFT, QC_FONT_BELOW_TARGET}
    ]
    if hard:
        raise TableTranslateError(f"TABLE_QC_HARD:{hard}")
    return codes, title, header, leftover


def _write_lines(page, lines: list[str], *, x: float = 36.0, y: float = 36.0) -> None:
    for line in lines:
        fontname, _ = _paint_font(line, bold=False)
        page.insert_text((x, y), line, fontname=_page_font(page, fontname, line), fontsize=10)
        y += 14


def append_mono_continuation(doc, *, title: str, header: list[str], rows: list[list[str]]) -> int:
    number = _table_number_from_title(title)
    prepare_embedded_font([title, CONTINUATION_LABEL, *header, *(c for r in rows for c in r)])
    page = doc.new_page()
    lines = [f"表 {number}{CONTINUATION_LABEL}"]
    if header:
        lines.append("  ".join(header))
    lines.extend("  ".join(row) for row in rows)
    _write_lines(page, lines)
    return len(doc) - 1


def append_dual_continuation(
    doc,
    origin_doc,
    source_page_index: int,
    *,
    title: str,
    header: list[str],
    rows: list[list[str]],
) -> int:
    import pymupdf

    plan_dual_continuations(source_page_index + 1, 1)
    prepare_embedded_font([title, CONTINUATION_LABEL, *header, *(c for r in rows for c in r)])
    src = origin_doc[source_page_index]
    page = doc.new_page(width=src.rect.width * 2, height=src.rect.height)
    left = pymupdf.Rect(0, 0, src.rect.width, src.rect.height)
    page.show_pdf_page(left, origin_doc, source_page_index)
    number = _table_number_from_title(title)
    lines = [f"表 {number}{CONTINUATION_LABEL}"]
    if header:
        lines.append("  ".join(header))
    lines.extend("  ".join(row) for row in rows)
    _write_lines(page, lines, x=src.rect.width + 36.0)
    return len(doc) - 1


def _table_number_from_title(title: str) -> int:
    digits = "".join(ch for ch in title if ch.isdigit())
    return int(digits) if digits else 1

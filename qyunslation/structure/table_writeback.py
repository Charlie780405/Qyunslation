# SPDX-License-Identifier: MPL-2.0
"""PLAN-033j：把已译表格块写回 PDF（矢量网格 + 可搜索文字 + 续页）。"""
from __future__ import annotations

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
    table_hard_fail_codes,
)
from .table_translate import (
    CONTINUATION_LABEL,
    TableTranslateError,
    plan_dual_continuations,
)

CJK_REGULAR = Path(
    os.environ.get("QYUNSLATION_FONT", "/home/dev/.fonts/NotoSansSC-Regular.otf")
)
CJK_BOLD = Path(
    os.environ.get("QYUNSLATION_FONT_BOLD", "/home/dev/.fonts/NotoSansSC-Bold.otf")
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_FONT_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
_PAGE_FONTS: dict[int, tuple[str, str]] = {}


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _paint_font(text: str, *, bold: bool):
    import pymupdf

    if _has_cjk(text):
        return "china-ss", pymupdf.Font("china-ss")
    return ("hebo" if bold else "helv"), pymupdf.Font("helv")


def _latin_name(bold: bool) -> str:
    return "hebo" if bold else "helv"


def _script_runs(text: str, *, bold: bool) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    buf: list[str] = []
    cjk: bool | None = None
    for ch in text:
        now = bool(_CJK_FONT_RE.match(ch))
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
    inset_x = 1.6
    inset_y = 0.55 if short else 1.0
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
    if inset.width < 20 and inset.height >= inset.width * 1.4:
        return _paint_cell_sideways(page, inset, text, fontname=fontname, font_size=size)
    page.draw_rect(inset, color=(1, 1, 1), fill=(1, 1, 1), width=0)
    mixed = _has_cjk(text) and re.search(r"[A-Za-z]", text or "")
    if mixed:
        return _paint_mixed(page, inset, text, bold=bold, font_size=size)
    while True:
        lines = _wrap_to_width(text, font=measure_font, font_size=size, width=inset.width)
        need_h = max(len(lines), 1) * size * 1.2
        if need_h <= inset.height + 0.3 or size <= 6.0:
            rc = page.insert_textbox(
                inset,
                "\n".join(lines),
                fontname=fontname,
                fontsize=size,
                align=0,
            )
            if rc >= 0 or size <= 6.0:
                return size
        size = max(6.0, size - 0.5)


def _paint_mixed(page, inset, text: str, *, bold: bool, font_size: float) -> float:
    import pymupdf

    fonts = {
        "helv": pymupdf.Font("helv"),
        "hebo": pymupdf.Font("helv"),
        "china-ss": pymupdf.Font("china-ss"),
    }
    size = max(6.0, float(font_size))
    leading = 1.15
    while True:
        lines: list[list[tuple[str, str]]] = [[]]
        line_w = 0.0
        for fname, chunk in _script_runs(text, bold=bold):
            font = fonts[fname]
            pieces = list(chunk) if fname == "china-ss" else (chunk.split(" ") if chunk.strip() else [chunk])
            for i, piece in enumerate(pieces):
                if fname != "china-ss" and i and piece:
                    piece = " " + piece
                w = float(font.text_length(piece, fontsize=size)) if piece else 0.0
                if lines[-1] and line_w + w > inset.width and piece.strip():
                    lines.append([])
                    line_w = 0.0
                    piece = piece.lstrip()
                    w = float(font.text_length(piece, fontsize=size)) if piece else 0.0
                if not piece:
                    continue
                if lines[-1] and lines[-1][-1][0] == fname:
                    lines[-1][-1] = (fname, lines[-1][-1][1] + piece)
                else:
                    lines[-1].append((fname, piece))
                line_w += w
        need_h = max(len(lines), 1) * size * leading
        if need_h <= inset.height + 0.3 or size <= 6.0:
            y = inset.y0 + size * 0.95
            for line in lines:
                if y > inset.y1 - 0.2:
                    break
                x = inset.x0
                for fname, chunk in line:
                    page.insert_text((x, y), chunk, fontname=fname, fontsize=size)
                    x += float(fonts[fname].text_length(chunk, fontsize=size))
                y += size * leading
            return size
        size = max(6.0, size - 0.5)


def _paint_cell_sideways(page, inset, text: str, *, fontname: str, font_size: float) -> float:
    import pymupdf

    size = max(3.0, float(font_size))
    while True:
        page.draw_rect(inset, color=(1, 1, 1), fill=(1, 1, 1), width=0)
        # 字号需落在短边内；文本长度沿长边。
        fits_width = size <= inset.width * 0.95
        fits_len = len(text) * size * 0.55 <= inset.height
        if (fits_width and fits_len) or size <= 3.0:
            origin = pymupdf.Point(inset.x0 + inset.width * 0.15, inset.y1 - 1.0)
            page.insert_text(
                origin,
                text,
                fontname=fontname,
                fontsize=size,
                rotate=90,
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
        if box_h >= box_w * 1.4:
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
) -> tuple[list[str], str, list[str], list[list[str]]]:
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
        if overflowing and _is_body_role(role):
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
            if "OVERFLOW" in str(exc) and _is_body_role(role):
                overflowing = True
                row = block.row_index if block.row_index is not None else 0
                if current_row != row:
                    flush_row()
                    current_row = row
                row_cells.append(result.text)
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
        page.insert_text((x, y), line, fontname=fontname, fontsize=10)
        y += 14


def append_mono_continuation(doc, *, title: str, header: list[str], rows: list[list[str]]) -> int:
    number = _table_number_from_title(title)
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

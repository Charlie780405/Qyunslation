# SPDX-License-Identifier: MPL-2.0
"""PLAN-033j：把已译表格块写回 PDF（矢量网格 + 可搜索文字 + 续页）。"""
from __future__ import annotations

import os
from pathlib import Path

from .models import BoundingBox, TranslatableBlock
from .role_fitter import (
    QC_FONT_BELOW_TARGET,
    QC_OVERFLOW,
    FitBlock,
    FitResult,
    hard_fail_codes,
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
    regular, bold = "noto-tbl-r", "noto-tbl-b"
    if CJK_REGULAR.is_file():
        page.insert_font(fontname=regular, fontfile=str(CJK_REGULAR))
    else:
        regular = "china-ss"
    if CJK_BOLD.is_file():
        page.insert_font(fontname=bold, fontfile=str(CJK_BOLD))
    else:
        bold = regular
    return regular, bold


def paint_cell(page, bbox: BoundingBox, text: str, *, bold: bool, font_size: float) -> float:
    import pymupdf

    rect = pymupdf.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    if rect.is_empty or rect.width < 2 or rect.height < 2:
        raise TableTranslateError("TABLE_CELL_BOX_INVALID")
    inset = pymupdf.Rect(rect.x0 + 0.6, rect.y0 + 0.6, rect.x1 - 0.6, rect.y1 - 0.6)
    if inset.is_empty:
        inset = rect
    regular, bold_name = _ensure_fonts(page)
    size = max(3.0, float(font_size))
    while True:
        page.draw_rect(inset, color=(1, 1, 1), fill=(1, 1, 1), width=0)
        rc = page.insert_textbox(
            inset,
            text,
            fontname=bold_name if bold else regular,
            fontsize=size,
            align=0,
        )
        if rc >= 0:
            return size
        if size <= 3.0:
            raise TableTranslateError("TABLE_OVERFLOW")
        size = max(3.0, size - 0.5)


def blocks_to_fit(blocks: list[TranslatableBlock], translations: dict[str, str]) -> list[FitBlock]:
    fitted = []
    for block in blocks:
        style = block.source_style
        size = float(style.font_size) if style and style.font_size else 9.0
        weight = (style.font_weight if style and style.font_weight else "regular") or "regular"
        box = block.bbox
        fitted.append(
            FitBlock(
                block_id=block.block_id,
                role=str(block.role or "table_cell"),
                source_text=block.source_text,
                translated_text=translations[block.block_id],
                source_size=size,
                source_bold=weight not in {"regular", "normal", None},
                box_w=float(box.x1 - box.x0) if box else 80.0,
                box_h=float(box.y1 - box.y0) if box else 16.0,
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
    hard = [code for code in hard_fail_codes(results) if code != QC_OVERFLOW]
    if hard:
        raise TableTranslateError(f"TABLE_QC_HARD:{hard}")
    return codes, title, header, leftover


def _write_lines(page, lines: list[str], *, x: float = 36.0, y: float = 36.0) -> None:
    regular, _bold = _ensure_fonts(page)
    for line in lines:
        page.insert_text((x, y), line, fontname=regular, fontsize=10)
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

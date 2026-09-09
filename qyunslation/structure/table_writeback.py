# SPDX-License-Identifier: MPL-2.0
"""PLAN-033j：把已译表格块写回 PDF（矢量网格 + 可搜索文字 + 续页）。"""
from __future__ import annotations

import os
from pathlib import Path

from .models import BoundingBox, TranslatableBlock
from .role_fitter import FitBlock, FitResult, hard_fail_codes
from .table_translate import (
    CONTINUATION_LABEL,
    TableTranslateError,
    plan_dual_continuations,
    plan_mono_continuations,
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


def paint_cell(page, bbox: BoundingBox, text: str, *, bold: bool, font_size: float) -> None:
    import pymupdf

    rect = pymupdf.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    if rect.is_empty or rect.width < 2 or rect.height < 2:
        raise TableTranslateError("TABLE_CELL_BOX_INVALID")
    inset = pymupdf.Rect(rect.x0 + 0.6, rect.y0 + 0.6, rect.x1 - 0.6, rect.y1 - 0.6)
    if inset.is_empty:
        inset = rect
    page.draw_rect(inset, color=(1, 1, 1), fill=(1, 1, 1), width=0)
    regular, bold_name = _ensure_fonts(page)
    rc = page.insert_textbox(
        inset,
        text,
        fontname=bold_name if bold else regular,
        fontsize=max(3.0, float(font_size)),
        align=0,
    )
    if rc < 0:
        raise TableTranslateError("TABLE_OVERFLOW")


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


def paint_fitted_blocks(
    page,
    blocks: list[TranslatableBlock],
    results: list[FitResult],
    *,
    x_min_frac: float | None,
) -> list[str]:
    codes: list[str] = []
    width = float(page.rect.width)
    for block, result in zip(blocks, results, strict=True):
        codes.extend(result.qc)
        if not block.bbox:
            raise TableTranslateError(f"TABLE_CELL_BOX_MISSING:{block.block_id}")
        paint_cell(
            page,
            output_bbox(block.bbox, width, x_min_frac=x_min_frac),
            result.text,
            bold=result.bold,
            font_size=result.font_size,
        )
    hard = hard_fail_codes(results)
    if hard:
        raise TableTranslateError(f"TABLE_QC_HARD:{hard}")
    return codes


def append_mono_continuation(doc, *, title: str, header: list[str], rows: list[list[str]]) -> int:
    import pymupdf

    pages = plan_mono_continuations(
        table_number=_table_number_from_title(title),
        title=title,
        header=header,
        rows=rows,
        rows_per_page=max(1, len(rows)),
    )
    page = doc.new_page()
    y = 36.0
    page.insert_text((36, y), pages[0].heading() if not pages[0].is_continuation else pages[-1].heading())
    y += 18
    for line in ([header] + rows):
        page.insert_text((36, y), "  ".join(line))
        y += 14
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
    y = 36.0
    x = src.rect.width + 36.0
    page.insert_text((x, y), f"{title}{CONTINUATION_LABEL}")
    y += 18
    for line in ([header] + rows):
        page.insert_text((x, y), "  ".join(line))
        y += 14
    return len(doc) - 1


def _table_number_from_title(title: str) -> int:
    digits = "".join(ch for ch in title if ch.isdigit())
    return int(digits) if digits else 1

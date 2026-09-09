# SPDX-License-Identifier: MPL-2.0
"""PLAN-033i：旋转无关的表格局部坐标与稳定单元格块。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .models import BlockRole, BoundingBox, SourceStyle, TranslationPolicy, TranslatableBlock
from .tables import TableRegion, _horizontal_lines, _vertical_lines

_TITLE_RE = re.compile(r"^\s*table\s+\d+\b", re.IGNORECASE)
_FOOTNOTE_RE = re.compile(r"^\s*(?:\*|†|‡|§|¶|[a-z]\)|[a-z]\s|note:|abbreviation)", re.I)
TABLE_OCR_MIN_DPI = 300


@dataclass(frozen=True, slots=True)
class TableLocalFrame:
    rotation: Literal[0, 90, 180, 270]
    x0: float
    y0: float
    width: float
    height: float

    def to_local(self, x: float, y: float) -> tuple[float, float]:
        dx, dy = x - self.x0, y - self.y0
        if self.rotation == 0:
            return dx, dy
        if self.rotation == 90:
            return dy, self.width - dx
        if self.rotation == 180:
            return self.width - dx, self.height - dy
        return self.height - dy, dx

    def to_page(self, u: float, v: float) -> tuple[float, float]:
        if self.rotation == 0:
            return self.x0 + u, self.y0 + v
        if self.rotation == 90:
            return self.x0 + self.width - v, self.y0 + u
        if self.rotation == 180:
            return self.x0 + self.width - u, self.y0 + self.height - v
        return self.x0 + v, self.y0 + self.height - u


@dataclass(frozen=True, slots=True)
class StructuredTableCell:
    block_id: str
    role: str
    text: str
    row_index: int
    column_index: int
    row_span: int = 1
    column_span: int = 1
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    font_weight: str = "regular"

    def as_block(self) -> TranslatableBlock:
        x0, y0, x1, y1 = self.bbox
        return TranslatableBlock(
            block_id=self.block_id,
            source_text=self.text,
            bbox=BoundingBox(x0=x0, y0=y0, x1=max(x1, x0 + 1.0), y1=max(y1, y0 + 1.0)),
            role=self.role,
            translation_policy=TranslationPolicy.TRANSLATE,
            source_style=SourceStyle(font_weight=self.font_weight),
            row_index=self.row_index,
            column_index=self.column_index,
            row_span=self.row_span,
            column_span=self.column_span,
        )


def infer_table_rotation(page, region: TableRegion) -> Literal[0, 90, 180, 270]:
    page_rot = int(getattr(page, "rotation", 0) or 0) % 360
    if page_rot in (90, 180, 270):
        return page_rot  # type: ignore[return-value]
    tall = (region.y1 - region.y0) > (region.x1 - region.x0) * 1.2
    page_portrait = float(page.rect.height) > float(page.rect.width)
    if tall and page_portrait:
        return 90
    return 0


def local_frame_for(page, region: TableRegion) -> TableLocalFrame:
    rot = infer_table_rotation(page, region)
    width = region.x1 - region.x0
    height = region.y1 - region.y0
    if rot in (90, 270):
        width, height = height, width
    return TableLocalFrame(
        rotation=rot,
        x0=region.x0,
        y0=region.y0,
        width=width,
        height=height,
    )


def _cluster(values: list[float], tol: float) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    groups = [[ordered[0]]]
    for value in ordered[1:]:
        if abs(value - groups[-1][-1]) <= tol:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _words_in_region(page, region: TableRegion) -> list[tuple[float, float, float, float, str]]:
    words: list[tuple[float, float, float, float, str]] = []
    try:
        raw = page.get_text("words") or []
    except Exception:
        raw = []
    for item in raw:
        if len(item) < 5:
            continue
        x0, y0, x1, y1, text = item[:5]
        cx, cy = (float(x0) + float(x1)) / 2.0, (float(y0) + float(y1)) / 2.0
        if region.x0 - 2 <= cx <= region.x1 + 2 and region.y0 - 2 <= cy <= region.y1 + 2:
            if str(text).strip():
                words.append((float(x0), float(y0), float(x1), float(y1), str(text)))
    if words:
        return words
    return ocr_table_region(page, region, dpi=TABLE_OCR_MIN_DPI)


def ocr_table_region(
    page, region: TableRegion, *, dpi: int = TABLE_OCR_MIN_DPI
) -> list[tuple[float, float, float, float, str]]:
    """仅对表格区域做 ≥300 DPI OCR。禁止整页/整表栅格化当终稿。"""
    dpi = max(int(dpi), TABLE_OCR_MIN_DPI)
    try:
        import pymupdf

        clip = pymupdf.Rect(region.x0, region.y0, region.x1, region.y1)
        pix = page.get_pixmap(clip=clip, dpi=dpi, alpha=False)
    except Exception:
        return []
    try:
        from qyunslation.extensions.image_translate import ocr_image

        boxes = ocr_image(pix.tobytes("png"), suffix=".png") or []
    except Exception:
        return []
    scale = dpi / 72.0
    out = []
    for box in boxes:
        if len(box) < 5:
            continue
        x0, y0, x1, y1, text = box[:5]
        out.append(
            (
                region.x0 + float(x0) / scale,
                region.y0 + float(y0) / scale,
                region.x0 + float(x1) / scale,
                region.y0 + float(y1) / scale,
                str(text),
            )
        )
    return out


def _assign_role(
    text: str,
    row: int,
    n_cols: int,
    n_rows: int,
    *,
    is_title: bool,
    header_row: int,
    filled_in_row: int,
) -> str:
    if is_title or _TITLE_RE.match(text):
        return BlockRole.TABLE_TITLE.value
    if _FOOTNOTE_RE.match(text) and row >= max(n_rows - 2, 1):
        return BlockRole.TABLE_FOOTNOTE.value
    if row == header_row:
        return BlockRole.TABLE_HEADER.value
    if filled_in_row == 1 and n_cols > 1:
        return BlockRole.TABLE_GROUP.value
    return BlockRole.TABLE_CELL.value


def structure_table(
    page,
    region: TableRegion,
    *,
    caption_text: str = "",
    number: int | None = None,
) -> list[StructuredTableCell]:
    table_no = int(number if number is not None else region.number)
    frame = local_frame_for(page, region)
    words = _words_in_region(page, region)
    h_lines = _horizontal_lines(page)
    v_lines = _vertical_lines(page)

    local_ys = [frame.to_local((x0 + x1) / 2.0, (y0 + y1) / 2.0)[1] for x0, y0, x1, y1, _ in words]
    local_xs = [frame.to_local((x0 + x1) / 2.0, (y0 + y1) / 2.0)[0] for x0, y0, x1, y1, _ in words]
    for x0, x1, y in h_lines:
        if region.y0 - 4 <= y <= region.y1 + 4:
            local_ys.append(frame.to_local((x0 + x1) / 2.0, y)[1])
    for y0, y1, x in v_lines:
        if region.x0 - 4 <= x <= region.x1 + 4:
            local_xs.append(frame.to_local(x, (y0 + y1) / 2.0)[0])

    row_centers = _cluster(local_ys, tol=max(frame.height * 0.04, 6.0))
    col_centers = _cluster(local_xs, tol=max(frame.width * 0.08, 8.0))
    if not row_centers:
        row_centers = [frame.height / 2.0]
    if not col_centers:
        col_centers = [frame.width / 2.0]

    buckets: dict[tuple[int, int], list[tuple[float, float, float, float, str]]] = {}
    for x0, y0, x1, y1, text in words:
        u, v = frame.to_local((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        row = min(range(len(row_centers)), key=lambda i: abs(row_centers[i] - v))
        col = min(range(len(col_centers)), key=lambda i: abs(col_centers[i] - u))
        buckets.setdefault((row, col), []).append((x0, y0, x1, y1, text))

    grid_has_title = any(
        _TITLE_RE.match(item[4] or "") for items in buckets.values() for item in items
    )
    if caption_text:
        cells = [
            StructuredTableCell(
                block_id=f"table:{table_no}:title",
                role=BlockRole.TABLE_TITLE.value,
                text=caption_text.strip(),
                row_index=0,
                column_index=0,
                column_span=len(col_centers),
                bbox=(region.x0, max(region.y0 - 18.0, 0.0), region.x1, region.y0 + 2.0),
            )
        ]
        row_offset = 1
    else:
        cells = []
        row_offset = 0

    filled_by_row: dict[int, int] = {}
    for (row, col), items in buckets.items():
        filled_by_row[row] = filled_by_row.get(row, 0) + 1

    n_rows = len(row_centers)
    n_cols = len(col_centers)
    for (row, col), items in sorted(buckets.items()):
        text = " ".join(item[4] for item in items).strip()
        if not text:
            continue
        xs0 = min(item[0] for item in items)
        ys0 = min(item[1] for item in items)
        xs1 = max(item[2] for item in items)
        ys1 = max(item[3] for item in items)
        is_title = bool(_TITLE_RE.match(text))
        header_row = 1 if (not caption_text and grid_has_title) else 0
        role = _assign_role(
            text,
            row,
            n_cols,
            n_rows,
            is_title=is_title,
            header_row=header_row,
            filled_in_row=filled_by_row.get(row, 0),
        )
        if caption_text and role == BlockRole.TABLE_TITLE.value:
            continue
        cells.append(
            StructuredTableCell(
                block_id=f"table:{table_no}:r{row + row_offset}c{col}",
                role=role,
                text=text,
                row_index=row + row_offset,
                column_index=col,
                bbox=(xs0, ys0, xs1, ys1),
            )
        )
    return cells


def table_blocks_for_manifest(
    page, region: TableRegion, *, caption_text: str = "", number: int | None = None
) -> list[TranslatableBlock]:
    return [
        cell.as_block()
        for cell in structure_table(
            page, region, caption_text=caption_text, number=number
        )
    ]

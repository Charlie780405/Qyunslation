# SPDX-License-Identifier: MPL-2.0
"""PLAN-033i：旋转无关的表格局部坐标与稳定单元格块。"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from .font_style import infer_font_weight
from .models import BlockRole, BoundingBox, SourceStyle, TranslationPolicy, TranslatableBlock
from .table_cell_policy import classify_cell_policy
from .tables import TableRegion, _horizontal_lines, _vertical_lines

_TITLE_RE = re.compile(r"^\s*table\s+\d+\b", re.IGNORECASE)
_FOOTNOTE_RE = re.compile(r"^\s*(?:\*|†|‡|§|¶|[a-z]\)|[a-z]\s|note:|abbreviation)", re.I)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_OR_PUNCT = re.compile(
    r"[\u4e00-\u9fff"
    r"\u3000-\u303f"  # CJK symbols/punct
    r"\uff00-\uffef"  # fullwidth forms
    r"、。；：？！「」『』（）【】《》]"
)
_TERMINAL_PUNCT = frozenset("。！？；.!?;")
_NUMBERED_START = re.compile(r"^[（(]?\d+[）).、．]|^\d+、")
TABLE_OCR_MIN_DPI = 300
# Baseline cluster tolerance (pt) for same visual line across fonts.
_LINE_Y_TOL = 3.0
TextUnit = tuple[float, float, float, float, str]


def _is_cjk_char(ch: str) -> bool:
    return bool(ch and _CJK_OR_PUNCT.match(ch))


def _span_needs_space(left: str, right: str) -> bool:
    """PLAN-044a：CJK/数字邻接零空格；Latin 词间保留单空格。"""
    if not left or not right:
        return False
    a, b = left[-1], right[0]
    if a.isspace() or b.isspace():
        return False
    if _is_cjk_char(a) or _is_cjk_char(b):
        return False
    if a.isdigit() and (b.isdigit() or b in ".,%/-"):
        return False
    if b.isdigit() and a in ".,%/-":
        return False
    return True


def join_span_texts(parts: list[str]) -> str:
    """Join OCR/PDF spans without inserting spaces inside CJK compounds."""
    out = ""
    for piece in parts:
        piece = str(piece or "").strip()
        if not piece:
            continue
        if not out:
            out = piece
            continue
        if _span_needs_space(out, piece):
            out = f"{out} {piece}"
        else:
            out = f"{out}{piece}"
    return out.strip()


def _line_buckets(items: list[TextUnit], *, tol: float = _LINE_Y_TOL) -> list[list[TextUnit]]:
    """Cluster spans into visual lines by mid-y, then sort each line by x0."""
    if not items:
        return []
    ordered = sorted(items, key=lambda it: ((float(it[1]) + float(it[3])) / 2.0, float(it[0])))
    lines: list[list[TextUnit]] = []
    centers: list[float] = []
    for item in ordered:
        cy = (float(item[1]) + float(item[3])) / 2.0
        if lines and abs(cy - centers[-1]) <= tol:
            lines[-1].append(item)
            n = len(lines[-1])
            centers[-1] = (centers[-1] * (n - 1) + cy) / n
        else:
            lines.append([item])
            centers.append(cy)
    for line in lines:
        line.sort(key=lambda it: float(it[0]))
    return lines


def _soft_merge_lines(line_texts: list[str]) -> str:
    """Merge soft-wrapped lines; keep a break before numbered starters."""
    cleaned = [t.strip() for t in line_texts if t and t.strip()]
    if not cleaned:
        return ""
    merged = cleaned[0]
    for nxt in cleaned[1:]:
        if (merged and merged[-1] in _TERMINAL_PUNCT) or _NUMBERED_START.match(nxt):
            merged = f"{merged} {nxt}"
            continue
        merged = join_span_texts([merged, nxt])
    return merged.strip()


def compose_cell_text(items: list[TextUnit], *, tol: float = _LINE_Y_TOL) -> str:
    """PLAN-044a：行分桶 + CJK 零空格 + 软换行合并。"""
    lines = _line_buckets(items, tol=tol)
    line_texts = [join_span_texts([str(it[4]) for it in line]) for line in lines]
    text = _soft_merge_lines(line_texts)
    # 源 PDF 偶发「2 周」类数字-CJK 内嵌空格，收掉
    text = re.sub(r"(?<=\d)\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=\d)", "", text)
    return text.strip()


@dataclass(frozen=True, slots=True)
class TableLocalFrame:
    rotation: Literal[0, 90, 180, 270]
    x0: float
    y0: float
    width: float
    height: float

    def to_local(self, x: float, y: float) -> tuple[float, float]:
        # width/height are *local* extents (swapped for 90/270). Map with the
        # unswapped region edges: local height == page-space region width.
        dx, dy = x - self.x0, y - self.y0
        if self.rotation == 0:
            return dx, dy
        if self.rotation == 90:
            return dy, self.height - dx
        if self.rotation == 180:
            return self.width - dx, self.height - dy
        return self.width - dy, dx

    def to_page(self, u: float, v: float) -> tuple[float, float]:
        if self.rotation == 0:
            return self.x0 + u, self.y0 + v
        if self.rotation == 90:
            return self.x0 + self.height - v, self.y0 + u
        if self.rotation == 180:
            return self.x0 + self.width - u, self.y0 + self.height - v
        return self.x0 + v, self.y0 + self.width - u


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
    font_size: float | None = None

    def as_block(self) -> TranslatableBlock:
        x0, y0, x1, y1 = self.bbox
        return TranslatableBlock(
            block_id=self.block_id,
            source_text=self.text,
            bbox=BoundingBox(x0=x0, y0=y0, x1=max(x1, x0 + 1.0), y1=max(y1, y0 + 1.0)),
            role=self.role,
            translation_policy=classify_cell_policy(self.text),
            source_style=SourceStyle(font_weight=self.font_weight, font_size=self.font_size),
            row_index=self.row_index,
            column_index=self.column_index,
            row_span=self.row_span,
            column_span=self.column_span,
        )


def _majority_line_dir(page, region: TableRegion) -> tuple[float, float] | None:
    """多数文字行方向；侧放表常见 (0, ±1)，正放为 (±1, 0)。"""
    try:
        import pymupdf

        clip = pymupdf.Rect(region.x0, region.y0, region.x1, region.y1)
        raw = page.get_text("dict", clip=clip) or {}
    except Exception:
        return None
    counts: Counter[tuple[float, float]] = Counter()
    for block in raw.get("blocks", []):
        for line in block.get("lines", []) or []:
            direction = line.get("dir") or (1.0, 0.0)
            if len(direction) < 2:
                continue
            dx, dy = float(direction[0]), float(direction[1])
            counts[(round(dx, 1), round(dy, 1))] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def infer_table_rotation(page, region: TableRegion) -> Literal[0, 90, 180, 270]:
    page_rot = int(getattr(page, "rotation", 0) or 0) % 360
    if page_rot in (90, 180, 270):
        return page_rot  # type: ignore[return-value]
    direction = _majority_line_dir(page, region)
    if direction is not None:
        dx, dy = direction
        if abs(dy) > abs(dx) * 1.5:
            return 90 if dy <= 0 else 270
        return 0
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


def _adaptive_cluster(
    values: list[float], *, floor: float, cap: float
) -> list[float]:
    """按间隙切轴，避免单链把整表并成一格。"""
    if not values:
        return []
    ordered = sorted(values)
    if len(ordered) == 1:
        return [ordered[0]]
    gaps = [b - a for a, b in zip(ordered, ordered[1:]) if b - a > 1e-6]
    if not gaps:
        return [ordered[0]]
    gmin, gmax = min(gaps), max(gaps)
    if gmax <= max(gmin * 2.2, floor):
        tol = min(floor, cap)
    else:
        mid = sorted(gaps)[len(gaps) // 2]
        small = [gap for gap in gaps if gap <= mid] or gaps
        jitter = sorted(small)[len(small) // 2]
        tol = min(max(jitter * 2.0, floor), cap)
    return _cluster(ordered, tol)


def _cluster_axes(frame: TableLocalFrame, local_xs: list[float], local_ys: list[float]) -> tuple[list[float], list[float]]:
    if frame.rotation in (90, 270):
        return (
            _adaptive_cluster(local_xs, floor=6.0, cap=14.0),
            _adaptive_cluster(local_ys, floor=3.0, cap=6.0),
        )
    return (
        _adaptive_cluster(local_xs, floor=6.0, cap=16.0),
        _adaptive_cluster(local_ys, floor=3.0, cap=8.0),
    )


def _unit_style(item: TextUnit) -> tuple[str, int]:
    if len(item) >= 7:
        return str(item[5] or ""), int(item[6] or 0)
    return "", 0


def _cell_font_weight(items: list[TextUnit]) -> str:
    names: Counter[str] = Counter()
    flags = 0
    for item in items:
        name, flag = _unit_style(item)
        names[name] += max(len(item[4]), 1)
        flags |= flag
    font_name = names.most_common(1)[0][0] if names else ""
    return infer_font_weight(font_name, flags_bold=bool(flags & 16))


def _cell_font_size(items: list[TextUnit]) -> float | None:
    sizes = [float(item[7]) for item in items if len(item) >= 8 and float(item[7] or 0) > 0]
    if not sizes:
        return None
    sizes.sort()
    return sizes[len(sizes) // 2]


def _lines_in_region(page, region: TableRegion) -> list[TextUnit]:
    lines: list[TextUnit] = []
    try:
        import pymupdf

        clip = pymupdf.Rect(region.x0, region.y0, region.x1, region.y1)
        raw = page.get_text("dict", clip=clip) or {}
    except Exception:
        return []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []) or []:
            spans = line.get("spans", []) or []
            text = "".join(str(span.get("text") or "") for span in spans).strip()
            if not text:
                continue
            bbox = line.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            fonts: Counter[str] = Counter()
            flags = 0
            sizes: list[float] = []
            for span in spans:
                piece = str(span.get("text") or "")
                fonts[str(span.get("font") or "")] += max(len(piece), 1)
                flags |= int(span.get("flags") or 0)
                if span.get("size"):
                    sizes.append(float(span["size"]))
            font_name = fonts.most_common(1)[0][0] if fonts else ""
            size = sizes[len(sizes) // 2] if sizes else 0.0
            lines.append((x0, y0, x1, y1, text, font_name, flags, size))
    return lines


def _words_in_region(page, region: TableRegion) -> list[TextUnit]:
    words: list[TextUnit] = []
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
                words.append((float(x0), float(y0), float(x1), float(y1), str(text), "", 0))
    if words:
        return words
    return ocr_table_region(page, region, dpi=TABLE_OCR_MIN_DPI)


def _spans_in_region(page, region: TableRegion) -> list[TextUnit]:
    units: list[TextUnit] = []
    try:
        import pymupdf

        clip = pymupdf.Rect(region.x0, region.y0, region.x1, region.y1)
        raw = page.get_text("dict", clip=clip) or {}
    except Exception:
        return []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []) or []:
            for span in line.get("spans", []) or []:
                text = str(span.get("text") or "").strip()
                if not text:
                    continue
                bbox = span.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                units.append(
                    (
                        float(bbox[0]),
                        float(bbox[1]),
                        float(bbox[2]),
                        float(bbox[3]),
                        text,
                        str(span.get("font") or ""),
                        int(span.get("flags") or 0),
                        float(span.get("size") or 0.0),
                    )
                )
    return units


def _text_units_in_region(page, region: TableRegion, frame: TableLocalFrame) -> list[TextUnit]:
    if frame.rotation in (90, 270):
        lines = _lines_in_region(page, region)
        if lines:
            return lines
    spans = _spans_in_region(page, region)
    if spans:
        return spans
    return _words_in_region(page, region)


def _seed_line_axes(
    frame: TableLocalFrame,
    *,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    local_xs: list[float],
    local_ys: list[float],
) -> None:
    u0, v0 = frame.to_local(x0, y0)
    u1, v1 = frame.to_local(x1, y1)
    if abs(u1 - u0) >= abs(v1 - v0):
        local_ys.append((v0 + v1) / 2.0)
    else:
        local_xs.append((u0 + u1) / 2.0)


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
                "",
                0,
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


def _edge_interval(edges: tuple[float, ...], value: float) -> int:
    return max(0, min(bisect_right(edges, value) - 1, len(edges) - 2))


def _vertical_boundary_at(region: TableRegion, x: float, y: float) -> bool:
    return any(
        abs(axis - x) <= 1.5 and start - 1.5 <= y <= end + 1.5
        for start, end, axis in region.vertical_segments
    )


def _horizontal_boundary_at(region: TableRegion, y: float, x: float) -> bool:
    return any(
        abs(axis - y) <= 1.5 and start - 1.5 <= x <= end + 1.5
        for start, end, axis in region.horizontal_segments
    )


def _vector_grid_cells(
    page,
    region: TableRegion,
    *,
    table_no: int,
    base_row_offset: int,
) -> list[StructuredTableCell]:
    """Map text to exact vector-grid cells, including missing-edge merges."""
    rows = region.row_edges
    columns = region.column_edges
    if len(rows) < 2 or len(columns) < 2:
        return []
    units = _spans_in_region(page, region) or _words_in_region(page, region)
    buckets: dict[tuple[int, int, int, int], list[TextUnit]] = {}
    for item in units:
        x0, y0, x1, y1, _text = item[:5]
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        row0 = _edge_interval(rows, cy)
        col0 = _edge_interval(columns, cx)
        row1 = row0 + 1
        col1 = col0 + 1
        while col0 > 0 and not _vertical_boundary_at(region, columns[col0], cy):
            col0 -= 1
        while col1 < len(columns) - 1 and not _vertical_boundary_at(
            region, columns[col1], cy
        ):
            col1 += 1
        while row0 > 0 and not _horizontal_boundary_at(region, rows[row0], cx):
            row0 -= 1
        while row1 < len(rows) - 1 and not _horizontal_boundary_at(
            region, rows[row1], cx
        ):
            row1 += 1
        buckets.setdefault((row0, row1, col0, col1), []).append(item)

    filled_by_row: dict[int, int] = {}
    for row0, _row1, _col0, _col1 in buckets:
        filled_by_row[row0] = filled_by_row.get(row0, 0) + 1

    cells: list[StructuredTableCell] = []
    n_rows = len(rows) - 1
    n_cols = len(columns) - 1
    for (row0, row1, col0, col1), items in sorted(buckets.items()):
        text = compose_cell_text(items)
        if not text:
            continue
        role = _assign_role(
            text,
            row0,
            n_cols,
            n_rows,
            is_title=bool(_TITLE_RE.match(text)),
            header_row=0,
            filled_in_row=filled_by_row.get(row0, 0),
        )
        cells.append(
            StructuredTableCell(
                block_id=f"table:{table_no}:r{row0 + base_row_offset}c{col0}",
                role=role,
                text=text,
                row_index=row0 + base_row_offset,
                column_index=col0,
                row_span=row1 - row0,
                column_span=col1 - col0,
                bbox=(columns[col0], rows[row0], columns[col1], rows[row1]),
                font_weight=_cell_font_weight(items),
                font_size=_cell_font_size(items),
            )
        )
    return cells


def structure_table(
    page,
    region: TableRegion,
    *,
    caption_text: str = "",
    number: int | None = None,
    base_row_offset: int = 0,
) -> list[StructuredTableCell]:
    table_no = int(number if number is not None else region.number)
    if region.detector == "vector_grid" and region.row_edges and region.column_edges:
        return _vector_grid_cells(
            page,
            region,
            table_no=table_no,
            base_row_offset=base_row_offset,
        )
    frame = local_frame_for(page, region)
    units = _text_units_in_region(page, region, frame)
    h_lines = _horizontal_lines(page)
    v_lines = _vertical_lines(page)

    local_ys = [
        frame.to_local((item[0] + item[2]) / 2.0, (item[1] + item[3]) / 2.0)[1]
        for item in units
    ]
    local_xs = [
        frame.to_local((item[0] + item[2]) / 2.0, (item[1] + item[3]) / 2.0)[0]
        for item in units
    ]
    for x0, x1, y in h_lines:
        if region.y0 - 4 <= y <= region.y1 + 4:
            _seed_line_axes(
                frame,
                x0=x0,
                y0=y,
                x1=x1,
                y1=y,
                local_xs=local_xs,
                local_ys=local_ys,
            )
    for y0, y1, x in v_lines:
        if region.x0 - 4 <= x <= region.x1 + 4:
            _seed_line_axes(
                frame,
                x0=x,
                y0=y0,
                x1=x,
                y1=y1,
                local_xs=local_xs,
                local_ys=local_ys,
            )

    col_centers, row_centers = _cluster_axes(frame, local_xs, local_ys)
    if not row_centers:
        row_centers = [frame.height / 2.0]
    if not col_centers:
        col_centers = [frame.width / 2.0]

    buckets: dict[tuple[int, int], list[TextUnit]] = {}
    for item in units:
        x0, y0, x1, y1, text = item[:5]
        u, v = frame.to_local((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        row = min(range(len(row_centers)), key=lambda i: abs(row_centers[i] - v))
        col = min(range(len(col_centers)), key=lambda i: abs(col_centers[i] - u))
        buckets.setdefault((row, col), []).append(item)

    grid_has_title = any(
        _TITLE_RE.match(item[4] or "") for items in buckets.values() for item in items
    )
    if caption_text:
        cells = [
            StructuredTableCell(
                block_id=f"table:{table_no}:title",
                role=BlockRole.TABLE_TITLE.value,
                text=caption_text.strip(),
                row_index=base_row_offset,
                column_index=0,
                column_span=len(col_centers),
                bbox=(region.x0, max(region.y0 - 18.0, 0.0), region.x1, region.y0 + 2.0),
            )
        ]
        row_offset = base_row_offset + 1
    else:
        cells = []
        row_offset = base_row_offset

    filled_by_row: dict[int, int] = {}
    for (row, col), items in buckets.items():
        filled_by_row[row] = filled_by_row.get(row, 0) + 1

    n_rows = len(row_centers)
    n_cols = len(col_centers)
    row_bands = _band_edges(row_centers, frame.height)
    col_bands = _band_edges(col_centers, frame.width)
    reading_reverse = frame.rotation == 90
    for (row, col), items in sorted(buckets.items()):
        text = compose_cell_text(items)
        if not text:
            continue
        u0, u1 = col_bands[col]
        v0, v1 = row_bands[row]
        corners = [
            frame.to_page(u0, v0),
            frame.to_page(u1, v0),
            frame.to_page(u0, v1),
            frame.to_page(u1, v1),
        ]
        xs0 = min(p[0] for p in corners)
        ys0 = min(p[1] for p in corners)
        xs1 = max(p[0] for p in corners)
        ys1 = max(p[1] for p in corners)
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
                font_weight=_cell_font_weight(items),
                font_size=_cell_font_size(items),
            )
        )
    return cells


def _band_edges(centers: list[float], span: float) -> list[tuple[float, float]]:
    if not centers:
        return [(0.0, span)]
    edges: list[tuple[float, float]] = []
    for index, center in enumerate(centers):
        lo = 0.0 if index == 0 else (centers[index - 1] + center) / 2.0
        hi = span if index == len(centers) - 1 else (center + centers[index + 1]) / 2.0
        edges.append((lo, hi))
    return edges


def table_grid_dimensions(
    page,
    region: TableRegion,
    *,
    caption_text: str = "",
    number: int | None = None,
    base_row_offset: int = 0,
) -> tuple[int, int]:
    """Return (row_count, column_count) for manifest TableObject fields."""

    cells = structure_table(
        page,
        region,
        caption_text=caption_text,
        number=number,
        base_row_offset=base_row_offset,
    )
    if not cells:
        return 0, 0
    max_row = max(cell.row_index + cell.row_span - 1 for cell in cells)
    max_col = max(cell.column_index + cell.column_span - 1 for cell in cells)
    return max_row + 1, max_col + 1


def table_blocks_for_manifest(
    page,
    region: TableRegion,
    *,
    caption_text: str = "",
    number: int | None = None,
    base_row_offset: int = 0,
) -> list[TranslatableBlock]:
    return [
        cell.as_block()
        for cell in structure_table(
            page,
            region,
            caption_text=caption_text,
            number=number,
            base_row_offset=base_row_offset,
        )
    ]

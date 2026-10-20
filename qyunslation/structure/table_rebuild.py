# SPDX-License-Identifier: MPL-2.0
"""PLAN-083: Hermes-style literature table rebuild (row rules + column projection).

Port of WeKnora ``rebuildLiteratureTable``:
- row boundaries from horizontal rules (not word-gap guessing);
- columns from x-projection of multi-segment data rows;
- fail closed when rules/columns/coverage are unreliable;
- cell text always comes from the PDF text layer (never HPD OCR).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

_NUMERIC_SEG_RE = re.compile(r"^[\s0-9.,±+\-−–—/()%≥≤<>*†‡]+$")
_NUMBER_TOKEN_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)?")
_VALUE_GROUP_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)?\s*\([^)]*\)")
_FOOTNOTE_START_RE = re.compile(
    r"^(?:[*†‡§¶]|[a-z]\s|(?i:abbreviations?|notes?|data|values|source)\b)"
)


@dataclass(frozen=True)
class TableWord:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)


@dataclass
class _Segment:
    text: str
    x0: float
    x1: float
    words: list[TableWord] = field(default_factory=list)


@dataclass
class _Line:
    words: list[TableWord]
    segs: list[_Segment] = field(default_factory=list)
    y_mid: float = 0.0


@dataclass
class RebuildResult:
    """Successful rebuild has empty ``reason`` and non-empty ``rows``."""

    rows: list[list[str]] = field(default_factory=list)
    cell_boxes: list[list[tuple[float, float, float, float]]] = field(default_factory=list)
    footnotes: list[str] = field(default_factory=list)
    reason: str = ""
    n_cols: int = 0
    col_bands: list[tuple[float, float]] = field(default_factory=list)
    row_bounds: list[float] = field(default_factory=list)
    row_source: str = ""  # "rules" | "text_lines" | "hpd_geometry"
    font_size: float = 8.0
    frame_extended_to: float | None = None

    @property
    def ok(self) -> bool:
        return not self.reason and bool(self.rows)


def table_rebuild_mode() -> str:
    """``literature`` (default) | ``off``."""
    raw = (os.environ.get("QYUNSLATION_TABLE_REBUILD") or "literature").strip().casefold()
    if raw in {"0", "false", "off", "no", "disable", "disabled"}:
        return "off"
    return "literature"


def rebuild_literature_table(
    words: Sequence[TableWord],
    rules: Sequence[float],
    *,
    box: tuple[float, float, float, float] | None,
    cell_rects: Sequence[tuple[float, float, float, float]] | None = None,
) -> RebuildResult:
    """Rebuild a literature table grid from text-layer words and horizontal rules."""
    fail = RebuildResult
    if box is None:
        return fail(reason="no_region")
    x0, y0, x1, y1 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    inside = [
        w
        for w in words
        if (w.x0 + w.x1) / 2 >= x0 - 2
        and (w.x0 + w.x1) / 2 <= x1 + 2
        and (w.y0 + w.y1) / 2 >= y0 - 2
        and (w.y0 + w.y1) / 2 <= y1 + 2
    ]
    if len(inside) < 4:
        return fail(reason="too_few_words")
    bounds = sorted(float(y) for y in rules if y0 - 2 <= float(y) <= y1 + 2)
    # Deduplicate nearly-identical rule y values.
    merged_bounds: list[float] = []
    for y in bounds:
        if not merged_bounds or abs(y - merged_bounds[-1]) > 1.5:
            merged_bounds.append(y)
    bounds = merged_bounds
    if len(bounds) < 3:
        return fail(reason="no_row_rules")

    lines = _cluster_lines(inside)
    last_rule = bounds[-1]
    intervals: list[tuple[float, float, list[_Line]]] = []
    for i in range(len(bounds) - 1):
        if bounds[i + 1] - bounds[i] >= 3.0:
            intervals.append((bounds[i], bounds[i + 1], []))
    if len(intervals) < 2:
        return fail(reason="no_row_rules")

    foot_lines: list[_Line] = []
    for line in lines:
        if line.y_mid >= last_rule:
            foot_lines.append(line)
        elif line.y_mid < bounds[0]:
            intervals[0][2].append(line)
        else:
            for iy0, iy1, bucket in intervals:
                if iy0 <= line.y_mid < iy1:
                    bucket.append(line)
                    break

    header_count = _header_count(intervals, cell_rects or [], bounds[0])
    if header_count >= len(intervals):
        return fail(reason="no_data_rows")
    header, body = intervals[:header_count], intervals[header_count:]

    spans: list[tuple[float, float]] = []
    for _, _, bucket in body:
        for line in bucket:
            if len(line.segs) >= 2:
                for w in line.words:
                    spans.append((w.x0, w.x1))
    bands = _union_bands(spans, gap=4.0)
    if len(bands) < 2:
        return fail(reason="too_few_columns")
    n_cols = len(bands)

    # PLAN-083b: three-line tables pack many numeric text lines into one rule interval.
    use_text_rows = any(
        sum(1 for line in bucket if _line_is_numeric_data(line)) >= 3 for _, _, bucket in body
    )
    row_source = "text_lines" if use_text_rows else "rules"

    def cells_of(iv: tuple[float, float, list[_Line]], *, is_header: bool, top_header: bool) -> list[str]:
        iy0, iy1, bucket = iv
        cells = [""] * n_cols

        def append_to(band: int, text: str) -> None:
            if not text or band < 0 or band >= n_cols:
                return
            if cells[band] and not (
                text.startswith(",") or text.startswith(")") or cells[band].endswith("(")
            ):
                cells[band] += " "
            cells[band] += text

        for line in sorted(bucket, key=lambda item: item.y_mid):
            # Section/label row: single segment that *starts* in column 0.
            if (
                (not is_header)
                and len(line.segs) == 1
                and _segment_starts_in_band0(line.segs[0], bands)
                and line.segs[0].x1 > bands[0][1] + 4.0
            ):
                append_to(0, line.segs[0].text)
                continue
            mid_spans = None
            if top_header and 2 <= len(line.segs) < n_cols:
                mid_spans = _bands_by_segment_spacing(line.segs, bands)
            for si, seg in enumerate(line.segs):
                if mid_spans is not None and mid_spans[si]:
                    for b in mid_spans[si]:
                        append_to(b, seg.text)
                    continue
                if is_header:
                    spanned = _bands_by_header_cell(seg, line, iy0, iy1, cell_rects or [], bands)
                    if spanned:
                        for b in spanned:
                            append_to(b, seg.text)
                        continue
                group: list[str] = []
                group_band = -1

                def flush() -> None:
                    nonlocal group, group_band
                    if group:
                        append_to(group_band, _join_words(group))
                    group = []

                for w in seg.words:
                    b = _nearest_band_center(w, bands) if is_header else _band_of_word(w, bands)
                    if b != group_band:
                        flush()
                        group_band = b
                    group.append(w.text)
                flush()
        return [c.strip() for c in cells]

    header_row = [""] * n_cols
    header_line_words: list[TableWord] = []
    for hi, iv in enumerate(header):
        for b, text in enumerate(cells_of(iv, is_header=True, top_header=hi < len(header) - 1)):
            if text:
                header_row[b] = (header_row[b] + " " + text).strip()
        for line in iv[2]:
            header_line_words.extend(line.words)
    rows: list[list[str]] = [header_row]
    row_y_ranges: list[tuple[float, float]] = [(header[0][0], header[-1][1])]
    row_word_lists: list[list[TableWord]] = [header_line_words]
    sparse = 0
    data_rows = 0

    if use_text_rows:
        for iv in body:
            split_rows = _split_interval_by_text_lines(iv[2], bands, n_cols)
            for cells, y_range, line_words in split_rows:
                non_empty = sum(1 for c in cells if c)
                if non_empty == 0:
                    continue
                data_rows += 1
                if non_empty <= 1:
                    sparse += 1
                rows.append(cells)
                row_y_ranges.append(y_range)
                row_word_lists.append(line_words)
    else:
        for iv in body:
            cells = cells_of(iv, is_header=False, top_header=False)
            non_empty = sum(1 for c in cells if c)
            if non_empty == 0:
                continue
            data_rows += 1
            if non_empty <= 1:
                sparse += 1
            rows.append(cells)
            row_y_ranges.append((iv[0], iv[1]))
            words_iv: list[TableWord] = []
            for line in iv[2]:
                words_iv.extend(line.words)
            row_word_lists.append(words_iv)

    if data_rows == 0:
        return fail(reason="no_data_rows")
    if data_rows >= 3 and sparse / data_rows >= 0.6:
        return fail(reason="collapsed_rows")
    if _has_collapsed_value_cells(rows):
        return fail(reason="collapsed_rows")

    body_lines: list[_Line] = []
    for _, _, bucket in intervals:
        body_lines.extend(bucket)
    if not _numbers_covered(body_lines, rows):
        return fail(reason="numbers_unplaced")

    cell_boxes: list[list[tuple[float, float, float, float]]] = []
    for ri, (ry0, ry1) in enumerate(row_y_ranges):
        words_r = row_word_lists[ri] if ri < len(row_word_lists) else []
        if words_r:
            ry0 = min(ry0, min(w.y0 for w in words_r))
            ry1 = max(ry1, max(w.y1 for w in words_r))
        cell_boxes.append([(bx0, ry0, bx1, ry1) for bx0, bx1 in bands])

    heights = sorted(w.height for w in inside if w.height > 0) or [8.0]
    font_size = max(6.0, float(heights[len(heights) // 2]))

    return RebuildResult(
        rows=rows,
        cell_boxes=cell_boxes,
        footnotes=_footnotes(foot_lines),
        reason="",
        n_cols=n_cols,
        col_bands=bands,
        row_bounds=bounds,
        row_source=row_source,
        font_size=font_size,
    )


def extract_words_from_page(page, box: tuple[float, float, float, float]) -> list[TableWord]:
    """Collect text-layer words inside ``box`` from a PyMuPDF page."""
    x0, y0, x1, y1 = box
    out: list[TableWord] = []
    try:
        raw = page.get_text("words") or []
    except Exception:
        return out
    for item in raw:
        if len(item) < 5:
            continue
        wx0, wy0, wx1, wy1, text = (
            float(item[0]),
            float(item[1]),
            float(item[2]),
            float(item[3]),
            str(item[4] or "").strip(),
        )
        if not text:
            continue
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        if x0 - 2 <= cx <= x1 + 2 and y0 - 2 <= cy <= y1 + 2:
            out.append(TableWord(text=text, x0=wx0, y0=wy0, x1=wx1, y1=wy1))
    return out


def extract_row_rules_from_page(page, box: tuple[float, float, float, float]) -> list[float]:
    """Horizontal rule y values that intersect the table region."""
    from qyunslation.structure.tables import _horizontal_lines

    x0, y0, x1, y1 = box
    width = max(1.0, x1 - x0)
    ys: list[float] = []
    for lx0, lx1, y in _horizontal_lines(page):
        if y < y0 - 2 or y > y1 + 2:
            continue
        overlap = min(lx1, x1) - max(lx0, x0)
        if overlap / width >= 0.35:
            ys.append(float(y))
    # Always include region top/bottom so sparse three-line tables still get intervals.
    ys.extend([float(y0), float(y1)])
    return sorted(ys)


def extend_frame_to_bottom_rule(
    page, box: tuple[float, float, float, float]
) -> tuple[tuple[float, float, float, float], float | None]:
    """PLAN-083b: stretch a header-only scan box down to the table bottom rule.

    Only extends when the gap contains continuous multi-column numeric text lines.
    Does not change global table detection thresholds.
    """
    from qyunslation.structure.tables import _horizontal_lines

    x0, y0, x1, y1 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    width = max(1.0, x1 - x0)
    try:
        page_h = float(page.rect.height)
    except Exception:
        page_h = y1 + 200.0
    candidates: list[float] = []
    try:
        hlines = _horizontal_lines(page)
    except Exception:
        return (x0, y0, x1, y1), None
    for lx0, lx1, y in hlines:
        y = float(y)
        if y <= y1 + 2.0 or y > page_h - 30.0:
            continue
        overlap = min(lx1, x1) - max(lx0, x0)
        if overlap / width >= 0.60:
            candidates.append(y)
    # Deduplicate.
    merged: list[float] = []
    for y in sorted(candidates):
        if not merged or y - merged[-1] > 1.5:
            merged.append(y)
    for cand in merged:
        probe = (x0, y1, x1, cand)
        words = extract_words_from_page(page, probe)
        if len(words) < 4:
            continue
        lines = _cluster_lines(words)
        if len(lines) < 3:
            continue
        heights = sorted(w.height for w in words if w.height > 0) or [10.0]
        med_h = max(2.0, heights[len(heights) // 2])
        gaps_ok = all(
            lines[i + 1].y_mid - lines[i].y_mid <= 2.5 * med_h for i in range(len(lines) - 1)
        )
        if not gaps_ok:
            continue
        numeric = sum(1 for line in lines if _line_is_numeric_data(line))
        multi = sum(1 for line in lines if len(line.segs) >= 2)
        if numeric < 0.5 * len(lines) or multi < 0.4 * len(lines):
            # Looks like body prose / footnotes — stop looking further.
            break
        return (x0, y0, x1, float(cand)), float(cand)
    return (x0, y0, x1, y1), None


def verify_hpd_grid_against_words(
    hpd_rows: Sequence[Sequence[str]],
    words: Sequence[TableWord],
    *,
    estimated_rows: int,
) -> bool:
    """Hermes-style HPD gate: numbers fit both ways and row count is plausible."""
    if not hpd_rows:
        return False
    word_tokens = _NUMBER_TOKEN_RE.findall(" ".join(w.text for w in words))
    hpd_tokens = _NUMBER_TOKEN_RE.findall(" ".join(c for row in hpd_rows for c in row))
    if word_tokens:
        covered = sum(1 for t in word_tokens if t in hpd_tokens or any(t in cell for row in hpd_rows for cell in row))
        if covered / len(word_tokens) < 0.90:
            return False
    if hpd_tokens:
        blob = " ".join(w.text for w in words)
        if any(t not in blob for t in hpd_tokens):
            return False
    if estimated_rows > 0 and len(hpd_rows) < 0.8 * estimated_rows:
        return False
    return True


def rebuild_from_page(
    page,
    box: tuple[float, float, float, float],
    *,
    allow_hpd_fallback: bool = True,
) -> RebuildResult:
    """Rebuild using text-layer words/rules; optional HPD geometry when rules are missing."""
    extended, frame_y = extend_frame_to_bottom_rule(page, box)
    words = extract_words_from_page(page, extended)
    rules = extract_row_rules_from_page(page, extended)
    result = rebuild_literature_table(words, rules, box=extended)
    result.frame_extended_to = frame_y
    if result.ok or result.reason != "no_row_rules" or not allow_hpd_fallback:
        return result
    fallback = _hpd_geometry_fallback(page, extended, words, prior=result)
    fallback.frame_extended_to = frame_y
    return fallback


def _hpd_geometry_fallback(
    page,
    box: tuple[float, float, float, float],
    words: Sequence[TableWord],
    *,
    prior: RebuildResult,
) -> RebuildResult:
    """Use HPD only for grid shape; cell text still comes from the text layer."""
    try:
        from qyunslation.structure.models import BoundingBox
        from qyunslation.structure.table_grid_hpd import hpd_grid, hpd_health
    except Exception:
        return prior
    if not hpd_health():
        return prior
    x0, y0, x1, y1 = box
    grid = hpd_grid(page, BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1))
    if grid.error or grid.not_a_table or not grid.rows or grid.n_cols < 2:
        return RebuildResult(reason=prior.reason or "hpd_failed")
    if not verify_hpd_grid_against_words(grid.rows, words, estimated_rows=len(grid.rows)):
        return RebuildResult(reason="hpd_unverified")
    lines = _cluster_lines(words)
    if len(lines) < 2:
        return RebuildResult(reason="hpd_unverified")
    # Prefer word-line count close to HPD rows; otherwise keep all lines as rows.
    use_lines = lines
    if len(lines) >= max(2, int(0.8 * len(grid.rows))):
        # Merge surplus lines toward HPD row count by nearest y.
        if len(lines) > len(grid.rows) * 1.5:
            use_lines = _downsample_lines(lines, len(grid.rows))
    spans = [(w.x0, w.x1) for line in use_lines if len(line.segs) >= 2 for w in line.words]
    bands = _union_bands(spans, gap=4.0)
    bands = _fit_band_count(bands, grid.n_cols, box_x0=x0, box_x1=x1)
    if len(bands) < 2:
        return RebuildResult(reason="too_few_columns")
    n_cols = len(bands)
    rows: list[list[str]] = []
    cell_boxes: list[list[tuple[float, float, float, float]]] = []
    for line in use_lines:
        cells = [""] * n_cols
        boxes = [(b0, line.y_mid - 5, b1, line.y_mid + 5) for b0, b1 in bands]
        # Expand row height from word extents on this line.
        if line.words:
            ly0 = min(w.y0 for w in line.words)
            ly1 = max(w.y1 for w in line.words)
            boxes = [(b0, ly0, b1, ly1) for b0, b1 in bands]
        for w in line.words:
            b = _band_of_word(w, bands)
            if cells[b] and not (w.text[:1] in ",.;:)" or cells[b].endswith("(")):
                cells[b] += " "
            cells[b] += w.text
        if any(cells):
            rows.append([c.strip() for c in cells])
            cell_boxes.append(boxes)
    if len(rows) < 2:
        return RebuildResult(reason="no_data_rows")
    if not _numbers_covered(use_lines, rows):
        return RebuildResult(reason="numbers_unplaced")
    return RebuildResult(
        rows=rows,
        cell_boxes=cell_boxes,
        footnotes=[],
        reason="",
        n_cols=n_cols,
        col_bands=bands,
        row_bounds=[],
        row_source="hpd_geometry",
        font_size=_median_font_size(words),
    )


def _downsample_lines(lines: Sequence[_Line], target: int) -> list[_Line]:
    if target <= 0 or len(lines) <= target:
        return list(lines)
    # Keep evenly spaced lines by index.
    if target == 1:
        return [lines[len(lines) // 2]]
    step = (len(lines) - 1) / (target - 1)
    idxs = sorted({min(len(lines) - 1, int(round(i * step))) for i in range(target)})
    return [lines[i] for i in idxs]


def _fit_band_count(
    bands: Sequence[tuple[float, float]],
    n_cols: int,
    *,
    box_x0: float,
    box_x1: float,
) -> list[tuple[float, float]]:
    bands = list(bands)
    if n_cols < 2:
        return bands
    while len(bands) > n_cols and len(bands) >= 2:
        # Merge the closest neighbouring bands.
        best_i, best_gap = 0, float("inf")
        for i in range(len(bands) - 1):
            gap = bands[i + 1][0] - bands[i][1]
            if gap < best_gap:
                best_i, best_gap = i, gap
        left, right = bands[best_i], bands[best_i + 1]
        bands = [
            *bands[:best_i],
            (left[0], right[1]),
            *bands[best_i + 2 :],
        ]
    while len(bands) < n_cols:
        # Split the widest band.
        widths = [(b[1] - b[0], i) for i, b in enumerate(bands)]
        _, i = max(widths)
        b0, b1 = bands[i]
        mid = (b0 + b1) / 2
        bands = [*bands[:i], (b0, mid), (mid, b1), *bands[i + 1 :]]
    if not bands:
        width = max(1.0, box_x1 - box_x0)
        step = width / n_cols
        bands = [(box_x0 + i * step, box_x0 + (i + 1) * step) for i in range(n_cols)]
    return bands


# ---- internals ----------------------------------------------------------------


def _median_font_size(words: Sequence[TableWord]) -> float:
    heights = sorted(w.height for w in words if w.height > 0) or [8.0]
    return max(6.0, float(heights[len(heights) // 2]))


def _segment_starts_in_band0(seg: _Segment, bands: Sequence[tuple[float, float]]) -> bool:
    if not bands:
        return False
    b0, b1 = bands[0]
    return seg.x0 <= b1 and (seg.x0 + seg.x1) / 2 <= b1 + 4.0


def _line_is_numeric_data(line: _Line) -> bool:
    if not line.segs:
        return False
    if len(line.segs) >= 2 and any(_NUMBER_TOKEN_RE.search(s.text) for s in line.segs[1:]):
        return True
    if len(line.segs) == 1 and _NUMERIC_SEG_RE.match(line.segs[0].text or ""):
        return bool(_NUMBER_TOKEN_RE.search(line.segs[0].text))
    return False


def _has_collapsed_value_cells(rows: Sequence[Sequence[str]]) -> bool:
    """Reject when a data cell packs multiple value groups (row collapse)."""
    for ri, row in enumerate(rows):
        if ri == 0:
            continue
        for ci, cell in enumerate(row):
            if ci == 0:
                continue
            if len(_VALUE_GROUP_RE.findall(cell or "")) >= 2:
                return True
    return False


def _split_interval_by_text_lines(
    bucket: Sequence[_Line],
    bands: Sequence[tuple[float, float]],
    n_cols: int,
) -> list[tuple[list[str], tuple[float, float], list[TableWord]]]:
    """Split one rule interval into logical rows using text-line geometry."""
    if not bucket or n_cols < 2 or not bands:
        return []
    heights = [w.height for line in bucket for w in line.words if w.height > 0] or [10.0]
    med_h = max(2.0, sorted(heights)[len(heights) // 2])
    out: list[tuple[list[str], tuple[float, float], list[TableWord]]] = []
    cur_cells: list[str] | None = None
    cur_y0 = cur_y1 = 0.0
    cur_words: list[TableWord] = []
    prev_y_mid = 0.0

    def flush() -> None:
        nonlocal cur_cells, cur_words
        if cur_cells is not None and any(cur_cells):
            out.append(([c.strip() for c in cur_cells], (cur_y0, cur_y1), list(cur_words)))
        cur_cells = None
        cur_words = []

    def append_cell(cells: list[str], band: int, text: str) -> None:
        if not text or band < 0 or band >= n_cols:
            return
        if cells[band] and not (
            text.startswith(",") or text.startswith(")") or cells[band].endswith("(")
        ):
            cells[band] += " "
        cells[band] += text

    for line in sorted(bucket, key=lambda item: item.y_mid):
        ly0 = min(w.y0 for w in line.words) if line.words else line.y_mid - 4
        ly1 = max(w.y1 for w in line.words) if line.words else line.y_mid + 4
        # Assign each word to a band.
        band_texts: list[str] = [""] * n_cols
        for w in line.words:
            b = _band_of_word(w, bands)
            append_cell(band_texts, b, w.text)
        band_texts = [c.strip() for c in band_texts]
        starts_label = bool(line.segs) and _segment_starts_in_band0(line.segs[0], bands)
        only_data = not band_texts[0] and any(band_texts[1:])
        is_section = (
            starts_label
            and not any(band_texts[1:])
            and not (len(line.segs) == 1 and _NUMERIC_SEG_RE.match(line.segs[0].text or ""))
        )
        close = cur_cells is not None and (line.y_mid - prev_y_mid) <= 0.35 * med_h
        if cur_cells is not None and (close or only_data) and not is_section:
            for b, text in enumerate(band_texts):
                if text:
                    append_cell(cur_cells, b, text)
            cur_y0 = min(cur_y0, ly0)
            cur_y1 = max(cur_y1, ly1)
            cur_words.extend(line.words)
            prev_y_mid = line.y_mid
            continue
        flush()
        if is_section:
            cur_cells = [band_texts[0] or (line.segs[0].text if line.segs else "")] + [""] * (
                n_cols - 1
            )
        else:
            cur_cells = list(band_texts)
        cur_y0, cur_y1 = ly0, ly1
        cur_words = list(line.words)
        prev_y_mid = line.y_mid
    flush()
    return out


def _cluster_lines(words: Sequence[TableWord]) -> list[_Line]:
    heights = sorted(w.height for w in words) or [2.0]
    med_h = max(2.0, heights[len(heights) // 2])
    ordered = sorted(words, key=lambda w: w.cy)
    lines: list[_Line] = []
    sum_y = 0.0
    for w in ordered:
        if lines and abs(w.cy - sum_y / len(lines[-1].words)) <= 0.55 * med_h:
            lines[-1].words.append(w)
            sum_y += w.cy
            lines[-1].y_mid = sum_y / len(lines[-1].words)
            continue
        lines.append(_Line(words=[w], y_mid=w.cy))
        sum_y = w.cy
    gap_seg = max(4.0, 1.1 * med_h)
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
        for w in line.words:
            if line.segs and w.x0 - line.segs[-1].x1 <= gap_seg:
                prev = line.segs[-1]
                if w.text[:1] in ",.;:)" or prev.text.endswith("("):
                    prev.text += w.text
                else:
                    prev.text += " " + w.text
                prev.x1 = max(prev.x1, w.x1)
                prev.words.append(w)
            else:
                line.segs.append(_Segment(text=w.text, x0=w.x0, x1=w.x1, words=[w]))
    return lines


def _union_bands(spans: Sequence[tuple[float, float]], *, gap: float) -> list[tuple[float, float]]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: s[0])
    bands = [[ordered[0][0], ordered[0][1]]]
    for x0, x1 in ordered[1:]:
        if x0 <= bands[-1][1] + gap:
            bands[-1][1] = max(bands[-1][1], x1)
        else:
            bands.append([x0, x1])
    return [(a, b) for a, b in bands]


def _header_count(
    intervals: Sequence[tuple[float, float, list[_Line]]],
    cell_rects: Sequence[tuple[float, float, float, float]],
    top: float,
) -> int:
    header_bottom = _header_bottom(cell_rects, top)
    count = 0
    if header_bottom is not None:
        while count < len(intervals) and intervals[count][1] <= header_bottom + 1.5:
            count += 1
    else:
        while count < len(intervals) and count < 4 and _numeric_in(intervals[count]) == 0:
            count += 1
    if count == 0:
        count = 1
    return count


def _header_bottom(
    cell_rects: Sequence[tuple[float, float, float, float]], top: float
) -> float | None:
    bottom, found = top, False
    changed = True
    while changed:
        changed = False
        for c in cell_rects:
            if c[1] <= bottom + 1.0 and c[3] > bottom + 1.0 and c[1] >= top - 3.0:
                bottom, found, changed = c[3], True, True
    return bottom if found else None


def _numeric_in(iv: tuple[float, float, list[_Line]]) -> int:
    n = 0
    for line in iv[2]:
        for i, seg in enumerate(line.segs):
            if i > 0 and _NUMERIC_SEG_RE.match(seg.text):
                n += 1
    return n


def _band_of_word(w: TableWord, bands: Sequence[tuple[float, float]]) -> int:
    best, best_overlap = -1, 0.0
    for i, (b0, b1) in enumerate(bands):
        overlap = min(w.x1, b1) - max(w.x0, b0)
        if overlap > best_overlap:
            best, best_overlap = i, overlap
    for i, (b0, b1) in enumerate(bands):
        if b0 <= w.cx <= b1:
            return i
    if best >= 0:
        return best
    return _nearest_band_center(w, bands)


def _nearest_band_center(w: TableWord, bands: Sequence[tuple[float, float]]) -> int:
    nearest, dist = 0, float("inf")
    for i, (b0, b1) in enumerate(bands):
        d = abs((b0 + b1) / 2 - w.cx)
        if d < dist:
            nearest, dist = i, d
    return nearest


def _bands_by_header_cell(
    seg: _Segment,
    line: _Line,
    y0: float,
    y1: float,
    cells: Sequence[tuple[float, float, float, float]],
    bands: Sequence[tuple[float, float]],
) -> list[int] | None:
    center = (seg.x0 + seg.x1) / 2
    best = None
    for c in cells:
        if c[1] > y1 or c[3] < y0 or center < c[0] or center > c[2]:
            continue
        if best is None or (c[2] - c[0]) < (best[2] - best[0]):
            best = c
    if best is None:
        return None
    width = best[2] - best[0]
    if abs(center - (best[0] + best[2]) / 2) > 0.12 * width:
        return None
    if len(seg.words) > 4 or (seg.x1 - seg.x0) > 0.6 * width:
        return None
    covered = [i for i, (b0, b1) in enumerate(bands) if best[0] <= (b0 + b1) / 2 <= best[2]]
    if len(covered) < 2:
        return None
    for other in line.segs:
        if other is seg:
            continue
        oc = (other.x0 + other.x1) / 2
        if best[0] <= oc <= best[2]:
            return None
    return covered


def _bands_by_segment_spacing(
    segs: Sequence[_Segment], bands: Sequence[tuple[float, float]]
) -> list[list[int]] | None:
    if any(len(seg.words) > 4 for seg in segs):
        return None
    centers = [(seg.x0 + seg.x1) / 2 for seg in segs]
    edges = [0.0] * (len(segs) + 1)
    for i in range(1, len(segs)):
        edges[i] = (centers[i - 1] + centers[i]) / 2
    edges[0] = centers[0] - (edges[1] - centers[0])
    edges[-1] = centers[-1] + (centers[-1] - edges[-2])
    out: list[list[int]] = []
    for i in range(len(segs)):
        covered = [
            b
            for b, (b0, b1) in enumerate(bands)
            if edges[i] <= (b0 + b1) / 2 < edges[i + 1]
        ]
        if len(covered) < 2:
            return None
        out.append(covered)
    return out


def _numbers_covered(lines: Iterable[_Line], rows: Sequence[Sequence[str]]) -> bool:
    joined = " ".join(c for row in rows for c in row)
    total = found = 0
    for line in lines:
        for w in line.words:
            for token in _NUMBER_TOKEN_RE.findall(w.text):
                total += 1
                if token in joined:
                    found += 1
    return total == 0 or found / total >= 0.99


def _footnotes(lines: Sequence[_Line]) -> list[str]:
    notes: list[str] = []
    for line in sorted(lines, key=lambda item: item.y_mid):
        text = " ".join(seg.text for seg in line.segs).strip()
        if not text:
            continue
        if not notes or _FOOTNOTE_START_RE.match(text):
            notes.append(text)
        else:
            notes[-1] += " " + text
    return notes


def _join_words(words: Sequence[str]) -> str:
    out: list[str] = []
    for i, w in enumerate(words):
        if i > 0 and not (
            w[:1] in ",.;:)" or (out and out[-1].endswith("("))
        ):
            out.append(" ")
        out.append(w)
    return "".join(out)

# SPDX-License-Identifier: MPL-2.0
"""PLAN-033i：旋转无关的表格局部坐标与稳定单元格块。"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
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


@dataclass
class StructureResult:
    """PLAN-048b：结构重建结果 + 网格来源元数据。"""

    cells: list[StructuredTableCell] = field(default_factory=list)
    grid_source: str = "geometry_center"  # hpd|gutter|geometry_center|not_a_table|vector_grid
    qc_codes: list[str] = field(default_factory=list)
    mismatch_rate: float = 0.0
    n_cols: int = 0
    n_rows: int = 0


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
        cols = _adaptive_cluster(local_xs, floor=6.0, cap=14.0)
        rows = _adaptive_cluster(local_ys, floor=3.0, cap=6.0)
    else:
        cols = _adaptive_cluster(local_xs, floor=6.0, cap=16.0)
        rows = _adaptive_cluster(local_ys, floor=3.0, cap=8.0)
    # PLAN-048b：删除 _merge_column_clusters（会把 nAb 并进浓度列）；
    # caption_rules 路径改走 HPD / 空隙投影，此函数仅作最后兜底。
    return cols, rows


def _merge_intervals(ivs: list[tuple[float, float]], *, gap: float = 0.5) -> list[tuple[float, float]]:
    if not ivs:
        return []
    ordered = sorted(ivs)
    merged: list[tuple[float, float]] = [ordered[0]]
    for a, b in ordered[1:]:
        la, lb = merged[-1]
        if a <= lb + gap:
            merged[-1] = (la, max(lb, b))
        else:
            merged.append((a, b))
    return merged


def data_row_gutters(
    lines: list[list[TextUnit]],
    frame: TableLocalFrame,
    *,
    min_gutter: float = 4.0,
) -> list[tuple[float, float]]:
    """PLAN-048b：数据行文字 x 区间投影的空隙 → 列分隔。

    跳过表头/脚注稀疏行；只用「单元数 ≥ max(3, 中位数)」的数据行，
    避免宽表头桥接整表空隙（表3 实证）。
    """
    if not lines:
        return []
    ns = sorted(len(ln) for ln in lines)
    med = ns[len(ns) // 2] if ns else 0
    data = [ln for ln in lines[1:] if len(ln) >= max(3, med)]
    if not data:
        data = [ln for ln in lines if len(ln) >= 2]
    ivs: list[tuple[float, float]] = []
    for ln in data:
        for item in ln:
            x0, y0, x1, y1 = item[:4]
            u0, _ = frame.to_local(float(x0), (float(y0) + float(y1)) / 2.0)
            u1, _ = frame.to_local(float(x1), (float(y0) + float(y1)) / 2.0)
            ivs.append((min(u0, u1), max(u0, u1)))
    merged = _merge_intervals(ivs)
    gutters: list[tuple[float, float]] = []
    for (a1, b1), (a2, b2) in zip(merged, merged[1:]):
        if a2 - b1 >= min_gutter:
            gutters.append((b1, a2))
    return gutters


def gutter_column_centers(
    lines: list[list[TextUnit]],
    frame: TableLocalFrame,
    *,
    min_gutter: float = 4.0,
) -> list[float]:
    """空隙投影 → 列中心（各墨迹簇中点）。"""
    if not lines:
        return []
    ns = sorted(len(ln) for ln in lines)
    med = ns[len(ns) // 2] if ns else 0
    data = [ln for ln in lines[1:] if len(ln) >= max(3, med)] or [ln for ln in lines if len(ln) >= 2]
    ivs: list[tuple[float, float]] = []
    for ln in data:
        for item in ln:
            x0, y0, x1, y1 = item[:4]
            u0, _ = frame.to_local(float(x0), (float(y0) + float(y1)) / 2.0)
            u1, _ = frame.to_local(float(x1), (float(y0) + float(y1)) / 2.0)
            ivs.append((min(u0, u1), max(u0, u1)))
    merged = _merge_intervals(ivs)
    if not merged:
        return []
    gutters = data_row_gutters(lines, frame, min_gutter=min_gutter)
    if not gutters and len(merged) == 1:
        return [(merged[0][0] + merged[0][1]) / 2.0]
    return [(a + b) / 2.0 for a, b in merged]


def _line_norm_blob(items: list[TextUnit]) -> str:
    from .table_grid_hpd import normalize_for_align

    return "".join(normalize_for_align(it[4]) for it in items)


def _is_n_eq_wrap_line(units: list[TextUnit]) -> bool:
    """几何行几乎全是 (N=130) 碎片 → 应并进上一行。"""
    from .table_grid_hpd import normalize_for_align

    toks = [normalize_for_align(u[4]) for u in units if str(u[4]).strip()]
    if len(toks) < 2:
        return False
    n_like = 0
    for tok in toks:
        if (
            tok.startswith("n=")
            or tok in {"n", "=", ",", "a", "(", ")"}
            or tok.isdigit()
            or (tok.endswith(")") and tok[:-1].isdigit())
        ):
            n_like += 1
    return n_like >= max(1, len(toks) - 1)


def _prev_ends_comma(units: list[TextUnit]) -> bool:
    texts = [str(u[4]).strip() for u in units if str(u[4]).strip()]
    data = texts[1:] if len(texts) > 1 else texts
    if not data:
        return False
    return sum(1 for t in data if t.endswith(",") or t.endswith("，")) >= max(1, len(data) // 2)


_HEADER_START = re.compile(r"^(?:dose|visit)\b", re.I)


def _looks_data_line(units: list[TextUnit]) -> bool:
    """Q2W/多个数值 → 数据行，禁止并进表头。"""
    texts = [str(u[4]).strip() for u in units if str(u[4]).strip()]
    n_data = 0
    for text in texts:
        if re.fullmatch(r"Q\d+W", text, re.I):
            n_data += 1
        elif re.search(r"\d", text) and not re.search(
            r"(?:mL|mg|µg|ug|week\s*\d)", text, re.I
        ):
            n_data += 1
    return n_data >= 2


def _looks_header_banner(units: list[TextUnit]) -> bool:
    """表头上行：少量短语、无两位数据数字。"""
    texts = [str(u[4]).strip() for u in units if str(u[4]).strip()]
    if not texts or len(texts) > 5 or _looks_data_line(units):
        return False
    blob = " ".join(texts)
    return not re.search(r"\d{2,}", blob)


def _looks_header_continuation(units: list[TextUnit]) -> bool:
    texts = [str(u[4]).strip() for u in units if str(u[4]).strip()]
    if not texts or _looks_data_line(units):
        return False
    return bool(_HEADER_START.match(texts[0]))


def _merge_geo_wrap_lines(
    lines: list[list[TextUnit]],
    hpd_rows: list[list[str]],
) -> list[list[TextUnit]]:
    """HPD 已并折行时，几何层也并：N= 续行、逗号折行、表头上下两行。"""
    if len(lines) < 2:
        return lines
    hpd_blobs = [_hpd_row_blob(row) for row in hpd_rows if any(str(c).strip() for c in row)]

    def best(blob: str) -> float:
        return max((_row_similarity(blob, hb) for hb in hpd_blobs), default=0.0)

    out: list[list[TextUnit]] = [list(lines[0])]
    for nxt in lines[1:]:
        prev = out[-1]
        blob_a = _line_norm_blob(prev)
        blob_b = _line_norm_blob(nxt)
        combo = blob_a + blob_b
        merge = (
            _is_n_eq_wrap_line(nxt)
            or _prev_ends_comma(prev)
            or (_looks_header_banner(prev) and _looks_header_continuation(nxt))
        )
        if not merge:
            score_c = best(combo)
            if score_c >= 0.45 and score_c > max(best(blob_a), best(blob_b)) + 0.05:
                merge = True
        if merge:
            merged = list(prev) + list(nxt)
            merged.sort(key=lambda u: (float(u[0]), float(u[1])))
            out[-1] = merged
        else:
            out.append(list(nxt))
    return out


def _hpd_row_blob(cells: list[str]) -> str:
    from .table_grid_hpd import normalize_for_align

    return "".join(normalize_for_align(c) for c in cells if c and str(c).strip())


def _near_token(a: str, b: str) -> bool:
    """短 token 允许 1 编辑距离（HPD OCR：O2W↔Q2W）。"""
    if not a or not b:
        return False
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if max(len(a), len(b)) > 6:
        return False
    # 简易 Levenshtein 上限 1
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    # 插入/删除 1
    if len(a) < len(b):
        a, b = b, a
    # a longer by 1
    j = 0
    skip = 0
    for ch in a:
        if j < len(b) and ch == b[j]:
            j += 1
        else:
            skip += 1
            if skip > 1:
                return False
    return True


def _unit_fits_cell(piece: str, norm_t: str, acc: str) -> bool:
    if not piece or not norm_t:
        return False
    trial = acc + piece
    if norm_t.startswith(trial) or trial.startswith(norm_t) or piece in norm_t:
        return True
    if acc and norm_t.startswith(acc) and piece in norm_t[len(acc) :]:
        return True
    if not acc and _near_token(piece, norm_t):
        return True
    if not acc and len(piece) <= 4 and any(
        _near_token(piece, norm_t[i : i + len(piece)])
        for i in range(max(0, len(norm_t) - len(piece) + 1))
    ):
        return True
    return False


def _row_similarity(geo_blob: str, hpd_blob: str) -> float:
    if not geo_blob or not hpd_blob:
        return 0.0

    def fold(s: str) -> str:
        return (
            s.replace("o2w", "q2w")
            .replace("o4w", "q4w")
            .replace("02w", "q2w")
            .replace("04w", "q4w")
        )

    geo_blob, hpd_blob = fold(geo_blob), fold(hpd_blob)
    a, b = geo_blob, hpd_blob
    if len(a) > len(b):
        a, b = b, a
    if a in b:
        return 1.0
    import re

    nums_a = set(re.findall(r"\d+(?:\.\d+)?", a))
    nums_b = set(re.findall(r"\d+(?:\.\d+)?", b))
    shared = nums_a & nums_b
    # 表头 µg mL-1 的孤立 "1" 不能当整行命中，否则折行无法合并
    distinctive = {n for n in shared if "." in n or len(n) >= 2}
    if distinctive:
        inter = len(shared) / max(len(nums_a | nums_b), 1)
    elif len(shared) >= 2:
        inter = len(shared) / max(len(nums_a | nums_b), 1)
    else:
        inter = 0.0
    pref = 0.0
    for n in range(min(12, len(a)), 3, -1):
        if a[:n] in b:
            pref = n / max(len(a), 1)
            break
    seq = SequenceMatcher(None, a, b).ratio()
    return max(inter, pref, seq)


def align_hpd_grid(
    lines: list[list[TextUnit]],
    hpd_rows: list[list[str]],
    *,
    mismatch_limit: float = 0.15,
) -> tuple[list[list[list[TextUnit]]], float, list[str]]:
    """PLAN-048b：按内容对齐几何行与 HPD 行，再行内左到右消耗 unit。

    HPD 常把 ``(N=130)`` 并进表头，导致行索引错位；故先做行相似度匹配。
    """
    from .table_grid_hpd import normalize_for_align

    qc: list[str] = []
    if not lines or not hpd_rows:
        return [], 1.0, ["HPD_GRID_MISMATCH"]

    n_cols = max((len(r) for r in hpd_rows), default=0)
    if n_cols < 1:
        return [], 1.0, ["NOT_A_TABLE"]

    hpd = [r for r in hpd_rows if any(str(c).strip() for c in r)]
    lines = _merge_geo_wrap_lines(lines, hpd)
    geo_blobs = [_line_norm_blob(ln) for ln in lines]
    hpd_blobs = [_hpd_row_blob(r) for r in hpd]

    # 为每个 HPD 行找最佳未用几何行
    used_geo: set[int] = set()
    pairs: list[tuple[int, int]] = []  # (hpd_i, geo_i)
    for hi, hb in enumerate(hpd_blobs):
        best_gi, best_score = -1, 0.15
        for gi, gb in enumerate(geo_blobs):
            if gi in used_geo:
                continue
            score = _row_similarity(gb, hb)
            if score > best_score:
                best_score, best_gi = score, gi
        if best_gi >= 0:
            used_geo.add(best_gi)
            pairs.append((hi, best_gi))

    # 也尝试把未匹配的几何行接到「部分包含」的 HPD（折行残留）
    cell_items: list[list[list[TextUnit]]] = [None] * len(hpd)  # type: ignore
    unused_units = 0
    total_units = sum(len(ln) for ln in lines)

    for hi, gi in pairs:
        units = list(lines[gi])
        targets = [(normalize_for_align(c), c) for c in (hpd[hi] + [""] * n_cols)[:n_cols]]
        row_buckets: list[list[TextUnit]] = [[] for _ in range(n_cols)]
        ui = 0
        for ci, (norm_t, _raw) in enumerate(targets):
            if not norm_t:
                continue
            acc = ""
            matched: list[TextUnit] = []
            while ui < len(units):
                piece = normalize_for_align(units[ui][4])
                if not piece:
                    ui += 1
                    continue
                if _unit_fits_cell(piece, norm_t, acc):
                    matched.append(units[ui])
                    if not acc and _near_token(piece, norm_t):
                        acc = norm_t  # 整格模糊命中
                    else:
                        trial = acc + piece
                        acc = trial if norm_t.startswith(trial) else (acc + piece)
                    ui += 1
                    if len(acc) >= len(norm_t) or acc == norm_t or piece == norm_t:
                        break
                    continue
                if matched:
                    break
                later = False
                for nj, (nt2, _) in enumerate(targets[ci + 1 :], start=ci + 1):
                    if nt2 and (
                        piece in nt2 or nt2.startswith(piece) or _near_token(piece, nt2)
                    ):
                        later = True
                        break
                if later:
                    break
                unused_units += 1
                ui += 1
            row_buckets[ci] = matched
        while ui < len(units):
            unused_units += 1
            ui += 1
        cell_items[hi] = row_buckets

    # 未配对的 HPD 行 → 空桶
    for hi in range(len(hpd)):
        if cell_items[hi] is None:
            cell_items[hi] = [[] for _ in range(n_cols)]

    # 未用几何行：若能并入某已有 HPD 行（折行 N=），追加到对应列
    for gi, ln in enumerate(lines):
        if gi in used_geo:
            continue
        gb = geo_blobs[gi]
        # 典型 N= 折行：并进上一数据行各列
        if all(
            normalize_for_align(u[4]).startswith("n=")
            or normalize_for_align(u[4]) in {"n", "=", ",", "a"}
            or not normalize_for_align(u[4])
            for u in ln
        ) or "n=" in gb:
            # 找最近已配对且 y 更靠上的行
            if pairs:
                # 挂到最后一个 pair 的对应列（按 x 最近）
                _hi, _ = pairs[-1]
                buckets = cell_items[_hi]
                for u in ln:
                    ux = (float(u[0]) + float(u[2])) / 2.0
                    # 选已有墨迹中心最近的列
                    best_c, best_d = 0, 1e9
                    for ci, items in enumerate(buckets):
                        if not items:
                            continue
                        cx = sum((float(it[0]) + float(it[2])) / 2.0 for it in items) / len(items)
                        d = abs(cx - ux)
                        if d < best_d:
                            best_d, best_c = d, ci
                    buckets[best_c].append(u)
                used_geo.add(gi)
                continue
        unused_units += len(ln)

    matched_units = total_units - unused_units
    rate = (unused_units / total_units) if total_units else 1.0
    # 若多数 unit 已归入，放宽 mismatch；行配对成功即视为结构可用
    if len(pairs) >= max(2, len(hpd) // 2) and rate <= 0.45:
        qc = []
    elif rate > mismatch_limit:
        qc.append("HPD_GRID_MISMATCH")
    return cell_items, rate, qc


def _cells_from_buckets(
    buckets: dict[tuple[int, int], list[TextUnit]],
    *,
    table_no: int,
    row_offset: int,
    n_cols: int,
    n_rows: int,
    caption_text: str,
    grid_has_title: bool,
    region: TableRegion,
) -> list[StructuredTableCell]:
    filled_by_row: dict[int, int] = {}
    for (row, _col), items in buckets.items():
        if items:
            filled_by_row[row] = filled_by_row.get(row, 0) + 1
    cells: list[StructuredTableCell] = []
    header_row = 1 if (not caption_text and grid_has_title) else 0
    for (row, col), items in sorted(buckets.items()):
        text = compose_cell_text(items)
        if not text:
            continue
        ink_x0 = min(float(it[0]) for it in items)
        ink_y0 = min(float(it[1]) for it in items)
        ink_x1 = max(float(it[2]) for it in items)
        ink_y1 = max(float(it[3]) for it in items)
        is_title = bool(_TITLE_RE.match(text))
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
                bbox=(ink_x0, ink_y0, ink_x1, ink_y1),
                font_weight=_cell_font_weight(items),
                font_size=_cell_font_size(items),
            )
        )
    return expand_cell_bboxes(cells, region)


def expand_cell_bboxes(
    cells: list[StructuredTableCell], region: TableRegion
) -> list[StructuredTableCell]:
    """PLAN-048：墨迹框扩到同行/同列邻格中线，避免窄格竖排旋转与OVERFLOW碎片。"""
    if len(cells) < 2:
        return cells
    titles = [c for c in cells if "title" in (c.role or "")]
    body = [c for c in cells if "title" not in (c.role or "")]
    if len(body) < 2:
        return cells
    by_row: dict[int, list[int]] = {}
    by_col: dict[int, list[int]] = {}
    boxes = [list(c.bbox) for c in body]
    for i, cell in enumerate(body):
        by_row.setdefault(int(cell.row_index), []).append(i)
        by_col.setdefault(int(cell.column_index), []).append(i)
    rx0, ry0, rx1, ry1 = (
        float(region.x0),
        float(region.y0),
        float(region.x1),
        float(region.y1),
    )
    for idxs in by_row.values():
        idxs = sorted(idxs, key=lambda i: body[i].column_index)
        for k, i in enumerate(idxs):
            # 只填邻格空隙，不拉到区域边——单格误扩会盖住整行
            left = boxes[i][0] if k == 0 else (boxes[idxs[k - 1]][2] + boxes[i][0]) / 2.0
            right = boxes[i][2] if k == len(idxs) - 1 else (boxes[i][2] + boxes[idxs[k + 1]][0]) / 2.0
            boxes[i][0] = min(boxes[i][0], left)
            boxes[i][2] = max(boxes[i][2], right)
    for idxs in by_col.values():
        idxs = sorted(idxs, key=lambda i: body[i].row_index)
        for k, i in enumerate(idxs):
            # 只填相邻行号的空隙；隔行（折行缺失）不往下拉，避免盖住错列
            prev_i = idxs[k - 1] if k else None
            next_i = idxs[k + 1] if k + 1 < len(idxs) else None
            adj_up = (
                prev_i is not None
                and int(body[i].row_index) - int(body[prev_i].row_index) == 1
            )
            adj_dn = (
                next_i is not None
                and int(body[next_i].row_index) - int(body[i].row_index) == 1
            )
            top = (boxes[prev_i][3] + boxes[i][1]) / 2.0 if adj_up else boxes[i][1]
            bot = (boxes[i][3] + boxes[next_i][1]) / 2.0 if adj_dn else boxes[i][3]
            boxes[i][1] = min(boxes[i][1], top)
            boxes[i][3] = max(boxes[i][3], bot)
    for idxs in by_row.values():
        ordered = sorted(idxs, key=lambda i: boxes[i][0])
        for a, b in zip(ordered, ordered[1:]):
            if boxes[a][2] > boxes[b][0] + 0.5:
                mid = (boxes[a][2] + boxes[b][0]) / 2.0
                boxes[a][2] = mid
                boxes[b][0] = mid
    for idxs in by_col.values():
        ordered = sorted(idxs, key=lambda i: boxes[i][1])
        for a, b in zip(ordered, ordered[1:]):
            if boxes[a][3] > boxes[b][1] + 0.5:
                mid = (boxes[a][3] + boxes[b][1]) / 2.0
                boxes[a][3] = mid
                boxes[b][1] = mid
    out = list(titles)
    for cell, box in zip(body, boxes):
        x0 = max(rx0, min(box[0], box[2] - 2.0))
        y0 = max(ry0, min(box[1], box[3] - 2.0))
        x1 = min(rx1, max(box[2], x0 + 2.0))
        y1 = min(ry1, max(box[3], y0 + 2.0))
        out.append(
            StructuredTableCell(
                block_id=cell.block_id,
                role=cell.role,
                text=cell.text,
                row_index=cell.row_index,
                column_index=cell.column_index,
                row_span=cell.row_span,
                column_span=cell.column_span,
                bbox=(x0, y0, x1, y1),
                font_weight=cell.font_weight,
                font_size=cell.font_size,
            )
        )
    return out


def _geometry_center_structure(
    page,
    region: TableRegion,
    frame: TableLocalFrame,
    units: list[TextUnit],
    *,
    table_no: int,
    caption_text: str,
    base_row_offset: int,
) -> StructureResult:
    """旧中心聚类路径（仅兜底；grid_source=geometry_center → 不落笔）。"""
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
                frame, x0=x0, y0=y, x1=x1, y1=y, local_xs=local_xs, local_ys=local_ys
            )
    for y0, y1, x in v_lines:
        if region.x0 - 4 <= x <= region.x1 + 4:
            _seed_line_axes(
                frame, x0=x, y0=y0, x1=x, y1=y1, local_xs=local_xs, local_ys=local_ys
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
    cells.extend(
        _cells_from_buckets(
            buckets,
            table_no=table_no,
            row_offset=row_offset,
            n_cols=len(col_centers),
            n_rows=len(row_centers),
            caption_text=caption_text,
            grid_has_title=grid_has_title,
            region=region,
        )
    )
    return StructureResult(
        cells=cells,
        grid_source="geometry_center",
        qc_codes=["GEOMETRY_CENTER_UNSAFE"],
        n_cols=len(col_centers),
        n_rows=len(row_centers),
    )


def _gutter_structure(
    page,
    region: TableRegion,
    frame: TableLocalFrame,
    units: list[TextUnit],
    *,
    table_no: int,
    caption_text: str,
    base_row_offset: int,
) -> StructureResult:
    """数据行空隙投影定列。"""
    lines = _line_buckets([(u[0], u[1], u[2], u[3], u[4]) for u in units])
    col_centers = gutter_column_centers(lines, frame)
    if len(col_centers) < 2:
        return StructureResult(
            cells=[],
            grid_source="gutter",
            qc_codes=["NOT_A_TABLE"],
            n_cols=len(col_centers),
        )
    # 行中心：各线 mid-y 的 local v
    row_centers: list[float] = []
    for ln in lines:
        ys = [(float(it[1]) + float(it[3])) / 2.0 for it in ln]
        xs = [(float(it[0]) + float(it[2])) / 2.0 for it in ln]
        if not ys:
            continue
        _u, v = frame.to_local(xs[0], sum(ys) / len(ys))
        row_centers.append(v)
    buckets: dict[tuple[int, int], list[TextUnit]] = {}
    for item in units:
        x0, y0, x1, y1, _text = item[:5]
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
    cells.extend(
        _cells_from_buckets(
            buckets,
            table_no=table_no,
            row_offset=row_offset,
            n_cols=len(col_centers),
            n_rows=len(row_centers),
            caption_text=caption_text,
            grid_has_title=grid_has_title,
            region=region,
        )
    )
    return StructureResult(
        cells=cells,
        grid_source="gutter",
        qc_codes=[],
        n_cols=len(col_centers),
        n_rows=len(row_centers),
    )


def _hpd_structure(
    page,
    region: TableRegion,
    frame: TableLocalFrame,
    units: list[TextUnit],
    *,
    table_no: int,
    caption_text: str,
    base_row_offset: int,
) -> StructureResult | None:
    """HPD 网格 + 行几何对齐。失败返回 None（调用方降级）。"""
    from .table_grid_hpd import hpd_grid, hpd_mode

    mode = hpd_mode()
    if mode == "off":
        return None
    if mode == "gutter":
        return None

    grid = hpd_grid(page, region)
    if grid.error:
        return None
    if grid.not_a_table or grid.n_rows < 2 or grid.n_cols < 2:
        return StructureResult(
            cells=[],
            grid_source="not_a_table",
            qc_codes=["NOT_A_TABLE"],
            n_cols=grid.n_cols,
            n_rows=grid.n_rows,
        )

    lines = _line_buckets([(u[0], u[1], u[2], u[3], u[4]) for u in units])
    cell_items, rate, qc = align_hpd_grid(lines, grid.rows)
    if "HPD_GRID_MISMATCH" in qc and rate > 0.55:
        # 对齐严重失败 → 仍可用 HPD 列数校准空隙投影
        gutter = _gutter_structure(
            page,
            region,
            frame,
            units,
            table_no=table_no,
            caption_text=caption_text,
            base_row_offset=base_row_offset,
        )
        if gutter.n_cols == grid.n_cols and gutter.cells:
            gutter.grid_source = "hpd"  # 列数经 HPD 确认
            gutter.qc_codes = ["HPD_COLS_GUTTER_GEOM"]
            return gutter
        return None

    buckets: dict[tuple[int, int], list[TextUnit]] = {}
    for ri, row_buckets in enumerate(cell_items):
        for ci, items in enumerate(row_buckets):
            if items:
                buckets[(ri, ci)] = items

    # 若对齐后有效格过少，降级
    filled = sum(1 for items in buckets.values() if items)
    if filled < max(4, grid.n_rows):
        gutter = _gutter_structure(
            page,
            region,
            frame,
            units,
            table_no=table_no,
            caption_text=caption_text,
            base_row_offset=base_row_offset,
        )
        if gutter.n_cols == grid.n_cols and gutter.cells:
            gutter.grid_source = "hpd"
            gutter.qc_codes = ["HPD_COLS_GUTTER_GEOM"]
            return gutter
        if "HPD_GRID_MISMATCH" in qc:
            return None

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
                column_span=grid.n_cols,
                bbox=(region.x0, max(region.y0 - 18.0, 0.0), region.x1, region.y0 + 2.0),
            )
        ]
        row_offset = base_row_offset + 1
    else:
        cells = []
        row_offset = base_row_offset
    cells.extend(
        _cells_from_buckets(
            buckets,
            table_no=table_no,
            row_offset=row_offset,
            n_cols=grid.n_cols,
            n_rows=len(cell_items),
            caption_text=caption_text,
            grid_has_title=grid_has_title,
            region=region,
        )
    )
    return StructureResult(
        cells=cells,
        grid_source="hpd",
        qc_codes=qc,
        mismatch_rate=rate,
        n_cols=grid.n_cols,
        n_rows=len(cell_items),
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
    return structure_table_ex(
        page,
        region,
        caption_text=caption_text,
        number=number,
        base_row_offset=base_row_offset,
    ).cells


def structure_table_ex(
    page,
    region: TableRegion,
    *,
    caption_text: str = "",
    number: int | None = None,
    base_row_offset: int = 0,
) -> StructureResult:
    """PLAN-048b：HPD 网格优先 → 空隙投影 → geometry_center（不落笔）。"""
    table_no = int(number if number is not None else region.number)
    if region.detector == "vector_grid" and region.row_edges and region.column_edges:
        cells = _vector_grid_cells(
            page,
            region,
            table_no=table_no,
            base_row_offset=base_row_offset,
        )
        return StructureResult(
            cells=cells,
            grid_source="vector_grid",
            n_cols=max((c.column_index for c in cells), default=-1) + 1,
            n_rows=max((c.row_index for c in cells), default=-1) + 1,
        )

    frame = local_frame_for(page, region)
    units = _text_units_in_region(page, region, frame)
    if not units:
        return StructureResult(cells=[], grid_source="empty", qc_codes=["NOT_A_TABLE"])

    # 1) HPD
    hpd_result = _hpd_structure(
        page,
        region,
        frame,
        units,
        table_no=table_no,
        caption_text=caption_text,
        base_row_offset=base_row_offset,
    )
    if hpd_result is not None:
        return hpd_result

    # 2) 空隙投影
    gutter = _gutter_structure(
        page,
        region,
        frame,
        units,
        table_no=table_no,
        caption_text=caption_text,
        base_row_offset=base_row_offset,
    )
    if gutter.cells and "NOT_A_TABLE" not in gutter.qc_codes and gutter.n_cols >= 2:
        return gutter

    # 3) 旧中心聚类（标记 unsafe，翻译链不得落笔）
    return _geometry_center_structure(
        page,
        region,
        frame,
        units,
        table_no=table_no,
        caption_text=caption_text,
        base_row_offset=base_row_offset,
    )


# 兼容：旧名保留给旧版列检测调用方。只合并明显的同一列碎片，
# 不参与现代 HPD/gutter 主路径，避免把真实相邻列合并。
def _merge_column_clusters(centers: list[float]) -> list[float]:
    """Merge only near-identical centers while preserving well-spaced columns."""
    ordered = sorted(float(value) for value in centers)
    if not ordered:
        return []
    groups: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        # 16pt is deliberately below the smallest realistic table-column gap
        # in our PDF fixtures; it only absorbs span/text-fragment jitter.
        if value - groups[-1][-1] <= 16.0:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


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

    result = structure_table_ex(
        page,
        region,
        caption_text=caption_text,
        number=number,
        base_row_offset=base_row_offset,
    )
    if result.n_rows or result.n_cols:
        return result.n_rows, result.n_cols
    cells = result.cells
    if not cells:
        return 0, 0
    max_row = max(cell.row_index + cell.row_span - 1 for cell in cells)
    max_col = max(cell.column_index + cell.column_span - 1 for cell in cells)
    return max_row + 1, max_col + 1


# scan/translate 读取最近一次 structure 元数据（单线程扫描安全）
_LAST_STRUCTURE_META: dict = {}


def last_structure_meta() -> dict:
    return dict(_LAST_STRUCTURE_META)


def table_blocks_for_manifest(
    page,
    region: TableRegion,
    *,
    caption_text: str = "",
    number: int | None = None,
    base_row_offset: int = 0,
) -> list[TranslatableBlock]:
    global _LAST_STRUCTURE_META
    result = structure_table_ex(
        page,
        region,
        caption_text=caption_text,
        number=number,
        base_row_offset=base_row_offset,
    )
    _LAST_STRUCTURE_META = {
        "grid_source": result.grid_source,
        "qc_codes": list(result.qc_codes),
        "mismatch_rate": result.mismatch_rate,
        "n_cols": result.n_cols,
        "n_rows": result.n_rows,
        "table_number": int(number if number is not None else region.number),
    }
    return [cell.as_block() for cell in result.cells]

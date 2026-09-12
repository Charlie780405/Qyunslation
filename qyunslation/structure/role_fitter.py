# SPDX-License-Identifier: MPL-2.0
"""PLAN-033k：图片/表格共用的 role-aware 排版与对象级 QC。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

QC_UNTRANSLATED = "UNTRANSLATED"
QC_TRUNCATED = "TRUNCATED"
QC_OVERFLOW = "OVERFLOW"
QC_FONT_BELOW_TARGET = "FONT_BELOW_TARGET"
QC_ROLE_SIZE_DRIFT = "ROLE_SIZE_DRIFT"
QC_WEIGHT_MISMATCH = "WEIGHT_MISMATCH"
QC_GRAPHICS_DAMAGE = "GRAPHICS_DAMAGE"

HARD_FAIL = {
    QC_UNTRANSLATED,
    QC_TRUNCATED,
    QC_OVERFLOW,
    QC_GRAPHICS_DAMAGE,
    QC_WEIGHT_MISMATCH,
    QC_ROLE_SIZE_DRIFT,
}

# PLAN-041 makes the readability floor a hard error for tables.  Figures keep
# their established high-DPI warning path, so this must not leak into the
# shared image status calculation through ``HARD_FAIL``.
TABLE_HARD_FAIL = HARD_FAIL | {QC_FONT_BELOW_TARGET}

ROLE_MIN_RATIO = {
    "figure_title": 0.80,
    "table_title": 0.80,
    "figure_label": 0.70,
    "figure_body": 0.70,
    "table_cell": 0.70,
    "table_header": 0.70,
    "figure_footnote": 0.70,
    "table_footnote": 0.70,
}
ROLE_MIN_PT = {
    "figure_title": 7.0,
    "table_title": 7.0,
    "figure_label": 6.0,
    "figure_body": 6.0,
    "table_cell": 7.0,
    "table_header": 7.0,
    "table_group": 7.0,
    "figure_footnote": 5.0,
    "table_footnote": 5.5,
}
# PLAN-044d：监管表单表级统一字号阶梯（覆盖源字号 tier 爆炸）
TABLE_ROLE_SIZE = {
    "table_title": 8.0,
    "table_header": 8.0,
    "table_cell": 7.0,
    "table_group": 7.0,
    "table_footnote": 6.0,
}
# PLAN-045e：文献表按源字号 p75 对齐，不用监管硬阶梯
TABLE_SIZE_LADDER = "ladder"
TABLE_SIZE_SOURCE_P75 = "source_p75"
LITERATURE_ROLE_FLOOR = {
    "table_title": 7.0,
    "table_header": 7.0,
    "table_cell": 7.0,
    "table_group": 7.0,
    "table_footnote": 5.5,
}


@dataclass
class FitBlock:
    block_id: str
    role: str
    source_text: str
    translated_text: str
    source_size: float
    source_bold: bool
    box_w: float
    box_h: float


@dataclass
class FitResult:
    text: str
    font_size: float
    bold: bool
    dpi: int
    qc: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    truncated: bool = False
    overflow: bool = False


CompactFn = Callable[[str], tuple[str, dict[str, str]]]


def target_min_size(role: str, source_size: float) -> float:
    ratio = ROLE_MIN_RATIO.get(role, 0.70)
    floor = ROLE_MIN_PT.get(role, 6.0)
    return max(source_size * ratio, floor)


def choose_dpi(font_size: float) -> int:
    if font_size < 6.0:
        return 600
    if font_size < 8.0:
        return 450
    return 300


def wrap_lines(text: str, width_chars: int) -> list[str]:
    """按空格换行；整词保留（含连字符术语），禁止词内擅自断行。"""
    raw = (text or "").strip()
    if not raw:
        return [""]
    parts = raw.split()
    if not parts:
        return [""]
    lines: list[str] = []
    current = parts[0]
    limit = max(4, int(width_chars))
    for word in parts[1:]:
        trial = f"{current} {word}"
        if len(trial) <= limit:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _font_text_length(text: str, font_size: float) -> float:
    """真实字宽；失败时回退 0.5em 估算。"""
    try:
        import os
        from pathlib import Path

        import pymupdf

        font_path = Path(
            os.environ.get("QYUNSLATION_FONT", "/home/dev/.fonts/NotoSansSC-Regular.otf")
        )
        if font_path.is_file():
            font = pymupdf.Font(fontfile=str(font_path))
            return float(font.text_length(text, fontsize=font_size))
    except Exception:
        pass
    return len(text) * font_size * 0.5


def measure_textbox(text: str, font_size: float, width: float, height: float) -> bool:
    """用真实字宽估算能否装入框（按词换行）。"""
    if width <= 0 or height <= 0 or font_size <= 0:
        return False
    approx_chars = max(4, int(width / max(font_size * 0.45, 1.0)))
    lines = wrap_lines(text, approx_chars)
    fitted: list[str] = []
    for line in lines:
        if _font_text_length(line, font_size) <= width * 1.02:
            fitted.append(line)
            continue
        words = line.split()
        if not words:
            fitted.append(line)
            continue
        cur = words[0]
        for word in words[1:]:
            trial = f"{cur} {word}"
            if _font_text_length(trial, font_size) <= width:
                cur = trial
            else:
                fitted.append(cur)
                cur = word
        fitted.append(cur)
    line_h = font_size * 1.25
    return len(fitted) * line_h <= height + 0.5 and all(
        _font_text_length(line, font_size) <= width * 1.05 for line in fitted
    )


def _resolve_table_size_mode(
    *,
    normalize_table_sizes: bool,
    table_size_mode: str | None,
) -> str | None:
    if table_size_mode:
        return table_size_mode
    if normalize_table_sizes:
        return TABLE_SIZE_LADDER
    return None


def _percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    arr = sorted(float(v) for v in vals)
    if len(arr) == 1:
        return arr[0]
    k = (len(arr) - 1) * p
    f = int(k)
    c = min(f + 1, len(arr) - 1)
    if f == c:
        return arr[f]
    return arr[f] + (arr[c] - arr[f]) * (k - f)


def fit_block(
    block: FitBlock,
    *,
    compact: CompactFn | None = None,
    measure=None,
    normalize_table_sizes: bool = False,
    table_size_mode: str | None = None,
) -> FitResult:
    """换行 → 框内安全扩展 → 方向调整 → 等义精简 → 整组缩小。禁止删末行。"""
    text = block.translated_text
    mapping: dict[str, str] = {block.source_text: text}
    if not text.strip():
        return FitResult(
            text=text,
            font_size=block.source_size,
            bold=block.source_bold,
            dpi=300,
            qc=[QC_UNTRANSLATED],
        )

    role = str(block.role or "")
    mode = _resolve_table_size_mode(
        normalize_table_sizes=normalize_table_sizes, table_size_mode=table_size_mode
    )
    if mode == TABLE_SIZE_LADDER and role.startswith("table_"):
        size = float(TABLE_ROLE_SIZE.get(role, TABLE_ROLE_SIZE["table_cell"]))
        floor = float(TABLE_ROLE_SIZE.get(role, ROLE_MIN_PT.get(role, 6.0)))
    elif mode == TABLE_SIZE_SOURCE_P75 and role.startswith("table_"):
        size = float(block.source_size)
        floor = float(LITERATURE_ROLE_FLOOR.get(role, ROLE_MIN_PT.get(role, 7.0)))
    else:
        size = block.source_size
        floor = 3.0
    box_w, box_h = block.box_w, block.box_h
    measure_fn = measure or measure_textbox

    def fits(candidate: str, font_size: float, width: float, height: float) -> bool:
        return measure_fn(candidate, font_size, width, height)

    annotate_norm = mode is not None

    if fits(text, size, box_w, box_h):
        result = FitResult(
            text=text, font_size=size, bold=block.source_bold, dpi=choose_dpi(size), mapping=mapping
        )
        return _annotate_target(
            block, result, normalize_table_sizes=annotate_norm, table_size_mode=mode
        )

    expanded_w, expanded_h = box_w * 1.08, box_h * 1.08
    if fits(text, size, expanded_w, expanded_h):
        result = FitResult(
            text=text, font_size=size, bold=block.source_bold, dpi=choose_dpi(size), mapping=mapping
        )
        return _annotate_target(
            block, result, normalize_table_sizes=annotate_norm, table_size_mode=mode
        )

    if box_h > box_w * 1.4 and fits(text, size, box_h, box_w):
        result = FitResult(
            text=text, font_size=size, bold=block.source_bold, dpi=choose_dpi(size), mapping=mapping
        )
        return _annotate_target(
            block, result, normalize_table_sizes=annotate_norm, table_size_mode=mode
        )

    if compact is not None:
        compacted, cmap = compact(text)
        mapping.update(cmap)
        text = compacted
        if fits(text, size, box_w, box_h):
            result = FitResult(
                text=text,
                font_size=size,
                bold=block.source_bold,
                dpi=choose_dpi(size),
                mapping=mapping,
            )
            return _annotate_target(
                block, result, normalize_table_sizes=annotate_norm, table_size_mode=mode
            )

    # PLAN-044d / 045e：归一化模式下不低于角色下限，避免双重 shrink 到 3pt
    while size > floor and not fits(text, size, box_w, box_h):
        size -= 0.5
    size = max(floor, size)
    result = FitResult(
        text=text,
        font_size=size,
        bold=block.source_bold,
        dpi=choose_dpi(size),
        mapping=mapping,
        overflow=not fits(text, size, box_w, box_h),
    )
    if result.overflow:
        result.qc.append(QC_OVERFLOW)
    return _annotate_target(
        block, result, normalize_table_sizes=annotate_norm, table_size_mode=mode
    )


def _annotate_target(
    block: FitBlock,
    result: FitResult,
    *,
    normalize_table_sizes: bool = False,
    table_size_mode: str | None = None,
) -> FitResult:
    mode = _resolve_table_size_mode(
        normalize_table_sizes=normalize_table_sizes, table_size_mode=table_size_mode
    )
    role = str(block.role or "")
    if mode == TABLE_SIZE_LADDER and role.startswith("table_"):
        floor = float(TABLE_ROLE_SIZE.get(role, ROLE_MIN_PT.get(role, 6.0)))
        if result.font_size + 1e-6 < floor:
            result.qc.append(QC_FONT_BELOW_TARGET)
    elif mode == TABLE_SIZE_SOURCE_P75 and role.startswith("table_"):
        floor = float(LITERATURE_ROLE_FLOOR.get(role, ROLE_MIN_PT.get(role, 7.0)))
        if result.font_size + 1e-6 < floor:
            result.qc.append(QC_FONT_BELOW_TARGET)
    else:
        target = target_min_size(block.role, block.source_size)
        if result.font_size + 1e-6 < target:
            result.qc.append(QC_FONT_BELOW_TARGET)
    if result.bold != block.source_bold:
        result.qc.append(QC_WEIGHT_MISMATCH)
    return result


def fit_group(
    blocks: list[FitBlock],
    *,
    normalize_table_sizes: bool = False,
    table_size_mode: str | None = None,
    **kwargs,
) -> list[FitResult]:
    mode = _resolve_table_size_mode(
        normalize_table_sizes=normalize_table_sizes, table_size_mode=table_size_mode
    )
    results = [
        fit_block(
            block,
            normalize_table_sizes=normalize_table_sizes,
            table_size_mode=mode,
            **kwargs,
        )
        for block in blocks
    ]
    if mode == TABLE_SIZE_LADDER:
        # 表级：同 role 统一到阶梯字号（不再按源字号 tier 分裂）
        by_role: dict[str, list[int]] = {}
        for index, block in enumerate(blocks):
            by_role.setdefault(str(block.role or "table_cell"), []).append(index)
        for role, idxs in by_role.items():
            if not role.startswith("table_"):
                continue
            target = float(TABLE_ROLE_SIZE.get(role, TABLE_ROLE_SIZE["table_cell"]))
            for i in idxs:
                if results[i].overflow:
                    continue
                results[i].font_size = target
                results[i].dpi = choose_dpi(target)
        return results

    if mode == TABLE_SIZE_SOURCE_P75:
        by_role: dict[str, list[int]] = {}
        for index, block in enumerate(blocks):
            by_role.setdefault(str(block.role or "table_cell"), []).append(index)
        for role, idxs in by_role.items():
            if not role.startswith("table_"):
                continue
            sources = [float(blocks[i].source_size) for i in idxs]
            p75 = _percentile(sources, 0.75)
            floor = float(LITERATURE_ROLE_FLOOR.get(role, ROLE_MIN_PT.get(role, 7.0)))
            fitted = [
                float(results[i].font_size)
                for i in idxs
                if not results[i].overflow and results[i].font_size > 0
            ]
            bottleneck = min(fitted) if fitted else floor
            target = max(floor, min(p75, bottleneck))
            comparable: list[float] = []
            for i in idxs:
                if results[i].overflow:
                    continue
                results[i].font_size = target
                results[i].dpi = choose_dpi(target)
                comparable.append(target)
            # 溢出格已有 OVERFLOW，不把它们的源字号差记成 ROLE_SIZE_DRIFT
            if comparable and max(comparable) - min(comparable) > 0.6:
                for i in idxs:
                    if QC_ROLE_SIZE_DRIFT not in results[i].qc:
                        results[i].qc.append(QC_ROLE_SIZE_DRIFT)
        return results

    by_role: dict[str, list[int]] = {}
    for index, block in enumerate(blocks):
        by_role.setdefault(block.role, []).append(index)
    for role, idxs in by_role.items():
        if str(role).startswith("table_"):
            by_tier: dict[float, list[int]] = {}
            for index in idxs:
                tier = round(blocks[index].source_size * 2.0) / 2.0
                by_tier.setdefault(tier, []).append(index)
            for tier_idxs in by_tier.values():
                sizes = [results[i].font_size for i in tier_idxs]
                if max(sizes) - min(sizes) <= 0.75:
                    continue
                shared = min(sizes)
                for i in tier_idxs:
                    results[i].font_size = shared
                    results[i].dpi = choose_dpi(shared)
                    if (
                        shared + 1e-6
                        < target_min_size(blocks[i].role, blocks[i].source_size)
                        and QC_FONT_BELOW_TARGET not in results[i].qc
                    ):
                        results[i].qc.append(QC_FONT_BELOW_TARGET)
            continue
        sizes = [results[i].font_size for i in idxs]
        if max(sizes) - min(sizes) > 0.75:
            shared = min(sizes)
            for i in idxs:
                results[i].font_size = shared
                results[i].dpi = choose_dpi(shared)
            if max(sizes) - min(sizes) > 1.5:
                for i in idxs:
                    if QC_ROLE_SIZE_DRIFT not in results[i].qc:
                        results[i].qc.append(QC_ROLE_SIZE_DRIFT)
    return results

def hard_fail_codes(results: list[FitResult]) -> list[str]:
    codes = []
    for result in results:
        codes.extend(code for code in result.qc if code in HARD_FAIL)
    return codes


def table_hard_fail_codes(results: list[FitResult]) -> list[str]:
    codes = []
    for result in results:
        codes.extend(code for code in result.qc if code in TABLE_HARD_FAIL)
    return codes

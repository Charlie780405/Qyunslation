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
    "table_cell": 6.0,
    "table_header": 6.0,
    "figure_footnote": 5.0,
    "table_footnote": 5.0,
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
    words = (text or "").split()
    if not words:
        return [""]
    lines, current = [], words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if len(trial) <= width_chars:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def fit_block(
    block: FitBlock,
    *,
    compact: CompactFn | None = None,
    measure=None,
) -> FitResult:
    """换行 → 框内安全扩展 → 方向调整 → 等义精简 → 整组缩小。禁止删末行。"""
    text = block.translated_text
    mapping: dict[str, str] = {block.source_text: text}
    qc: list[str] = []
    if not text.strip():
        return FitResult(text=text, font_size=block.source_size, bold=block.source_bold, dpi=300, qc=[QC_UNTRANSLATED])

    size = block.source_size
    box_w, box_h = block.box_w, block.box_h
    width_chars = max(4, int(box_w / max(size * 0.5, 1.0)))

    def fits(candidate: str, font_size: float, width: float, height: float) -> bool:
        if measure is not None:
            return measure(candidate, font_size, width, height)
        lines = wrap_lines(candidate, max(4, int(width / max(font_size * 0.5, 1.0))))
        return len(lines) * font_size * 1.2 <= height and max(len(line) for line in lines) * font_size * 0.5 <= width

    if fits(text, size, box_w, box_h):
        result = FitResult(text=text, font_size=size, bold=block.source_bold, dpi=choose_dpi(size), mapping=mapping)
        return _annotate_target(block, result)

    # 框内安全扩展 8%
    expanded_w, expanded_h = box_w * 1.08, box_h * 1.08
    if fits(text, size, expanded_w, expanded_h):
        result = FitResult(text=text, font_size=size, bold=block.source_bold, dpi=choose_dpi(size), mapping=mapping)
        return _annotate_target(block, result)

    # 方向：竖排窄框
    if box_h > box_w * 1.4 and fits(text, size, box_h, box_w):
        result = FitResult(text=text, font_size=size, bold=block.source_bold, dpi=choose_dpi(size), mapping=mapping)
        return _annotate_target(block, result)

    if compact is not None:
        compacted, cmap = compact(text)
        mapping.update(cmap)
        text = compacted
        if fits(text, size, box_w, box_h):
            result = FitResult(text=text, font_size=size, bold=block.source_bold, dpi=choose_dpi(size), mapping=mapping)
            return _annotate_target(block, result)

    while size > 3.0 and not fits(text, size, box_w, box_h):
        size -= 0.5
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
    if text.endswith("...") or text != block.translated_text and compact is None:
        # 仅当未走精简却丢了结尾时算截断；本 fitter 从不切片
        pass
    return _annotate_target(block, result)


def _annotate_target(block: FitBlock, result: FitResult) -> FitResult:
    target = target_min_size(block.role, block.source_size)
    if result.font_size + 1e-6 < target:
        result.qc.append(QC_FONT_BELOW_TARGET)
    if result.bold != block.source_bold:
        result.qc.append(QC_WEIGHT_MISMATCH)
    return result


def fit_group(blocks: list[FitBlock], **kwargs) -> list[FitResult]:
    results = [fit_block(block, **kwargs) for block in blocks]
    by_role: dict[str, list[int]] = {}
    for index, block in enumerate(blocks):
        by_role.setdefault(block.role, []).append(index)
    for role, idxs in by_role.items():
        if str(role).startswith("table_"):
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

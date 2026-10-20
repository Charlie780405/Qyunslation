# SPDX-License-Identifier: MPL-2.0
"""PLAN-080d：译后让下划线等文字装饰线跟随译文，而不是留在英文原文的位置与宽度。

BabelDOC 只重写文字，不重写矢量图形：源文里画在文字下面的下划线（常见于超链接和小标题）
仍留在原坐标，译文重排后就出现 线比文字长、线悬在空白处、线压在别的文字下面。

做法（只处理能确定是"文字装饰"的线，其余保持原样）：

1. 在**源**页里找水平细线，要求它紧贴某一文本行下沿、宽度不超过该行文字宽度，并且不是表格线
   （线两端附近没有垂直细线）。满足的才算装饰线。
2. 译文页里，同坐标的那条线就是它的副本。找到它现在所在的译文行：
   * 找到了：把线裁到译文行的实际文字范围内；
   * 没有，但 8pt 内有横向重叠的译文行：把线挪到那一行的下沿；
   * 都没有：删除（悬空线比没有线更误导）。
3. 删除原线用"只删完全落在小矩形内的矢量线、不动文字和图片"的涂抹，再按原颜色和线宽画新线。

不是装饰线的线（表格线、分隔线、页眉页脚线、两端有垂直线的线）一律不动。
任何一步出错都保留原文件，不影响交付。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

MODE_ENV = "QYUNSLATION_DECORATION_REALIGN"

MAX_THICKNESS = 1.5       # pt，水平线的最大高度
MIN_WIDTH = 5.0           # pt，更短的线是项目符号/页码装饰，不处理
UNDERLINE_BELOW = 3.0     # pt，线可以低于文本行下沿这么多
UNDERLINE_ZONE = 0.35     # 线必须落在文本行下部 35% 以内（否则可能是删除线或别的线）
MAX_OVER_TEXT = 4.0       # pt，源文里线比文字最多宽这么多才算"贴着文字的下划线"
RELOCATE_WITHIN = 8.0     # pt，找不到同行文字时，最远向上/下找多远
MIN_RESULT_WIDTH = 16.0   # pt，裁剪/挪位后短于此的线直接删除（不到两个汉字宽的一小截不像下划线）
MIN_KEEP_RATIO = 0.25     # 裁剪后短于原线的这个比例也直接删除：原线盖的文字（如网址）译文里已不存在
GRID_TOLERANCE = 2.0      # pt，端点附近有垂直线则视为表格线


def realign_mode() -> str:
    value = (os.environ.get(MODE_ENV) or "off").strip().lower()
    return "on" if value in {"on", "1", "true", "yes"} else "off"


@dataclass
class Segment:
    x0: float
    x1: float
    y: float
    thickness: float
    color: tuple[float, ...] | None

    @property
    def width(self) -> float:
        return self.x1 - self.x0


@dataclass
class RealignReport:
    pages: int = 0
    candidates: int = 0
    kept: int = 0
    trimmed: int = 0
    moved: int = 0
    removed: int = 0
    skipped_grid: int = 0
    skipped_shared: int = 0
    skipped_reason: str | None = None
    failed_pages: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "candidates": self.candidates,
            "kept": self.kept,
            "trimmed": self.trimmed,
            "moved": self.moved,
            "removed": self.removed,
            "skipped_grid": self.skipped_grid,
            "skipped_shared": self.skipped_shared,
            "skipped_reason": self.skipped_reason,
            "failed_pages": list(self.failed_pages),
        }


def _text_lines(page: pymupdf.Page, x_offset: float = 0.0) -> list[tuple[float, float, float, float]]:
    """文本行外接框 (x0, y0, x1, y1)；只取有可见字符的 span 的并集。"""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            if x1 <= x_offset:
                continue
            lines.append((max(x0, x_offset), y0, x1, y1))
    return lines


def _thin_segments(page: pymupdf.Page) -> list[Segment]:
    segments = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.height > MAX_THICKNESS or rect.width < MIN_WIDTH:
            continue
        color = drawing.get("color") or drawing.get("fill")
        thickness = float(drawing.get("width") or rect.height or 0.5)
        segments.append(
            Segment(rect.x0, rect.x1, (rect.y0 + rect.y1) / 2.0, max(thickness, 0.3), tuple(color) if color else None)
        )
    return segments


def _vertical_segments(page: pymupdf.Page) -> list[tuple[float, float, float]]:
    out = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.width <= MAX_THICKNESS and rect.height >= MIN_WIDTH:
            out.append(((rect.x0 + rect.x1) / 2.0, rect.y0, rect.y1))
    return out


def _is_grid_line(seg: Segment, verticals: list[tuple[float, float, float]]) -> bool:
    for x, y0, y1 in verticals:
        if y0 - GRID_TOLERANCE <= seg.y <= y1 + GRID_TOLERANCE and (
            abs(x - seg.x0) <= GRID_TOLERANCE or abs(x - seg.x1) <= GRID_TOLERANCE
        ):
            return True
    return False


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return min(a1, b1) - max(a0, b0)


def _under_line(seg: Segment, line: tuple[float, float, float, float]) -> bool:
    """线是否贴着这一文本行的下沿，并且横向主要落在这行文字上。"""
    x0, y0, x1, y1 = line
    height = max(y1 - y0, 1.0)
    if not (y1 - UNDERLINE_ZONE * height <= seg.y <= y1 + UNDERLINE_BELOW):
        return False
    return _overlap(seg.x0, seg.x1, x0, x1) >= 0.5 * min(seg.width, x1 - x0)


def source_decorations(src_page: pymupdf.Page) -> tuple[list[Segment], int]:
    """源页中确认是文字装饰的线，以及因为是表格线而排除的线数。"""
    lines = _text_lines(src_page)
    verticals = _vertical_segments(src_page)
    found, grid = [], 0
    for seg in _thin_segments(src_page):
        best = None
        for line in lines:
            if _under_line(seg, line):
                width = _overlap(seg.x0, seg.x1, line[0], line[2])
                if best is None or width > best[1]:
                    best = (line, width)
        if best is None:
            continue
        line = best[0]
        if seg.width > (line[2] - line[0]) + MAX_OVER_TEXT:
            continue  # 比文字宽得多：分隔线或框线，不是下划线
        if _is_grid_line(seg, verticals):
            grid += 1
            continue
        found.append(seg)
    return found, grid


def _same_segment(a: Segment, b: Segment, offset: float) -> bool:
    return (
        abs(a.x0 + offset - b.x0) <= 0.6
        and abs(a.x1 + offset - b.x1) <= 0.6
        and abs(a.y - b.y) <= 0.6
    )


def _long_enough(width: float, original: Segment) -> bool:
    return width >= MIN_RESULT_WIDTH and width >= MIN_KEEP_RATIO * original.width


def plan_line(seg: Segment, lines: list[tuple[float, float, float, float]]) -> tuple[str, Segment | None]:
    """决定一条（已平移到译文页坐标的）装饰线怎么处理：keep / trim / move / remove。"""
    best = None
    for line in lines:
        if _under_line(seg, line):
            width = _overlap(seg.x0, seg.x1, line[0], line[2])
            if best is None or width > best[1]:
                best = (line, width)
    if best is not None:
        line = best[0]
        x0, x1 = max(seg.x0, line[0]), min(seg.x1, line[2])
        if abs(x0 - seg.x0) <= 1.0 and abs(x1 - seg.x1) <= 1.0:
            return "keep", None
        if not _long_enough(x1 - x0, seg):
            return "remove", None
        return "trim", Segment(x0, x1, seg.y, seg.thickness, seg.color)

    near = None
    for line in lines:
        gap = 0.0
        if seg.y < line[1]:
            gap = line[1] - seg.y
        elif seg.y > line[3]:
            gap = seg.y - line[3]
        if gap > RELOCATE_WITHIN:
            continue
        width = _overlap(seg.x0, seg.x1, line[0], line[2])
        if not _long_enough(width, seg):
            continue
        if near is None or (gap, -width) < (near[1], -near[2]):
            near = (line, gap, width)
    if near is None:
        return "remove", None
    line = near[0]
    x0, x1 = max(seg.x0, line[0]), min(seg.x1, line[2])
    return "move", Segment(x0, x1, line[3] - 1.0, seg.thickness, seg.color)


def _erase_rect(seg: Segment) -> pymupdf.Rect:
    pad = seg.thickness / 2.0 + 0.4
    return pymupdf.Rect(seg.x0 - 0.5, seg.y - pad, seg.x1 + 0.5, seg.y + pad)


def _erase_is_safe(seg: Segment, rect: pymupdf.Rect, drawings: list[pymupdf.Rect]) -> bool:
    """涂抹按"触碰即删"执行（零高度的描边线用"完全覆盖"删不掉），
    所以只有当擦除矩形碰到的矢量图形只有这条线自己时才执行；碰到别的（底纹、表格线、
    合并路径）就放弃这一条，保持原样。"""
    for other in drawings:
        if other.x1 < rect.x0 or other.x0 > rect.x1 or other.y1 < rect.y0 or other.y0 > rect.y1:
            continue
        is_target = (
            other.height <= MAX_THICKNESS
            and abs(other.x0 - seg.x0) <= 0.6
            and abs(other.x1 - seg.x1) <= 0.6
            and abs((other.y0 + other.y1) / 2.0 - seg.y) <= 0.6
        )
        if not is_target:
            return False
    return True


def plan_page(
    src_page: pymupdf.Page, out_page: pymupdf.Page
) -> tuple[list[tuple[str, Segment, Segment | None]], int]:
    """只读：这一页每条装饰线该怎么处理（keep / trim / move / remove），以及被排除的表格线数。

    ``realign_page`` 据此执行；QA 据此判断"还有多少线没跟上译文"，两边用同一套判断。
    """
    decorations, grid = source_decorations(src_page)
    if not decorations:
        return [], grid
    offset = max(out_page.rect.width - src_page.rect.width, 0.0)
    if offset < src_page.rect.width * 0.5:  # 单页（mono）：没有并排的原文半幅
        offset = 0.0
    lines = _text_lines(out_page, x_offset=offset)
    out_segments = _thin_segments(out_page)

    actions: list[tuple[str, Segment, Segment | None]] = []
    for deco in decorations:
        match = next((s for s in out_segments if _same_segment(deco, s, offset)), None)
        if match is None:
            continue  # 译文页里这条线已经不在原处（别的补丁动过），不碰
        action, new = plan_line(match, lines)
        actions.append((action, match, new))
    return actions, grid


def realign_page(src_page: pymupdf.Page, out_page: pymupdf.Page, report: RealignReport) -> None:
    actions, grid = plan_page(src_page, out_page)
    report.skipped_grid += grid
    report.candidates += len(actions)
    if not actions:
        return

    drawings = [d["rect"] for d in out_page.get_drawings()]
    applied: list[tuple[str, Segment | None]] = []
    for action, old, new in actions:
        if action == "keep":
            report.kept += 1
            continue
        rect = _erase_rect(old)
        if not _erase_is_safe(old, rect, drawings):
            report.skipped_shared += 1
            continue
        out_page.add_redact_annot(rect, fill=False)
        applied.append((action, new))
    if not applied:
        return
    out_page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
        text=pymupdf.PDF_REDACT_TEXT_NONE,
    )
    for action, new in applied:
        if action == "remove":
            report.removed += 1
        elif new is not None:
            out_page.draw_line(
                (new.x0, new.y),
                (new.x1, new.y),
                color=new.color or (0, 0, 0),
                width=new.thickness,
            )
            report.trimmed += action == "trim"
            report.moved += action == "move"


def _drop_pending_redactions(page: pymupdf.Page) -> None:
    """页面处理中途失败时，清掉还没应用的涂抹标注，避免留在文件里。"""
    try:
        for annot in list(page.annots(types=[pymupdf.PDF_ANNOT_REDACT]) or []):
            page.delete_annot(annot)
    except Exception:  # noqa: BLE001
        pass


def realign_pdf(source: Path, output: Path, destination: Path | None = None) -> RealignReport:
    """对 ``output`` 做装饰线随文；``destination`` 缺省时原地替换。出错的页保持原样。"""
    report = RealignReport()
    src = pymupdf.open(source)
    doc = pymupdf.open(output)
    try:
        if len(src) != len(doc):
            # 交替页的 dual（页数是源文的两倍）、缺页或多页：页与页对不上，宁可不处理也不错位
            report.skipped_reason = f"page_count_mismatch source={len(src)} output={len(doc)}"
            if destination is not None and destination != output:
                import shutil

                shutil.copyfile(output, destination)  # 调用方指定了目标文件时，原样交付
            return report
        for index in range(min(len(src), len(doc))):
            report.pages += 1
            try:
                realign_page(src[index], doc[index], report)
            except Exception:  # noqa: BLE001 — 单页失败不影响其他页
                report.failed_pages.append(index + 1)
                _drop_pending_redactions(doc[index])
        target = destination or output
        tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        doc.save(tmp, garbage=0, deflate=True)
    finally:
        doc.close()
        src.close()
    os.replace(tmp, destination or output)
    return report

# SPDX-License-Identifier: MPL-2.0
"""横向（旋转）整页：先转正再翻译，译后转回去。全部 fail-open。

期刊的宽表常把整页内容旋转 90° 印在竖版页面上（文字方向是竖的，页面本身 ``/Rotate`` 为 0）。BabelDOC 只认水平文字，
这类页面里的表格和说明文字整页被跳过，译文页还是英文。做法：

1. 翻译前 ``normalize_rotated_pages``：把这些页的内容流包一层 ``cm`` 矩阵转正，页面框随之横过来（文字在内容流里真
   的变成水平，BabelDOC 与后面的表格重排都按正常横版页处理）。边车 ``rotations.json`` 记原页尺寸与转向。
2. 译后 ``finish_rotated_pages``：用 ``show_pdf_page(rotate=...)`` 把译好的横版页转回原方向；双语页（左原文右译文的
   并排页）左半直接换回原件页，右半转回。

开关 ``QYUNSLATION_ROTATED_PAGES``（默认 on，``0`` 关闭）。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SIDECAR = "rotations.json"
MIN_CHARS = 200
MIN_SHARE = 0.6


def rotation_enabled() -> bool:
    return (os.environ.get("QYUNSLATION_ROTATED_PAGES") or "1").strip().casefold() not in {"0", "off", "false", "no"}


def _import_fitz():
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover
        import fitz  # type: ignore[import-not-found,no-redef]
    return fitz


@dataclass
class RotatedPage:
    page: int  # 0-based
    cw: int  # 转正时顺时针转的角度：90 或 270
    width: float  # 原页宽（竖版）
    height: float  # 原页高
    keep: list[list[float]] | None = None  # 原页上横排的行（页脚、页码）外框；转正后它们变竖排会被引擎丢掉

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_rotated_pages(doc) -> dict[int, int]:
    """页号(0-based) → 转正所需的顺时针角度（90 / 270）。竖排字符占多数才算。"""
    found: dict[int, int] = {}
    for index, page in enumerate(doc):
        if page.rotation:
            continue
        counts = {"up": 0, "down": 0, "flat": 0}
        try:
            blocks = page.get_text("dict").get("blocks") or []
        except Exception:  # noqa: BLE001
            continue
        for block in blocks:
            for line in block.get("lines") or []:
                size = sum(len(str(s.get("text") or "").strip()) for s in line.get("spans") or [])
                if not size:
                    continue
                dx, dy = line.get("dir") or (1.0, 0.0)
                if abs(dy) > 0.9:
                    counts["up" if dy < 0 else "down"] += size
                elif abs(dx) > 0.9:
                    counts["flat"] += size
        total = sum(counts.values())
        vertical = max(counts["up"], counts["down"])
        if total and vertical >= MIN_CHARS and vertical / total >= MIN_SHARE:
            found[index] = 90 if counts["up"] >= counts["down"] else 270
    return found


def _matrix(cw: int, box) -> tuple[tuple[float, ...], tuple[float, float]]:
    """内容流 cm 矩阵与新页框尺寸。cw=90：自下而上的文字转成自左向右。"""
    x0, y0, x1, y1 = float(box.x0), float(box.y0), float(box.x1), float(box.y1)
    if cw == 90:
        return (0.0, -1.0, 1.0, 0.0, -y0, x1), (y1 - y0, x1 - x0)
    return (0.0, 1.0, -1.0, 0.0, y1, -x0), (y1 - y0, x1 - x0)


def _flat_line_rects(page) -> list[list[float]]:
    """原页上横排行的外框（页脚版权行、页码）。整页转正后它们会变成竖排，BabelDOC 会把它们丢掉。"""
    rects: list[list[float]] = []
    try:
        blocks = page.get_text("dict").get("blocks") or []
    except Exception:  # noqa: BLE001
        return rects
    for block in blocks:
        for line in block.get("lines") or []:
            dx, dy = line.get("dir") or (1.0, 0.0)
            text = "".join(str(s.get("text") or "") for s in line.get("spans") or []).strip()
            if text and abs(dx) > 0.9 and line.get("bbox"):
                x0, y0, x1, y1 = (float(v) for v in line["bbox"])
                rects.append([x0 - 1.0, y0 - 1.0, x1 + 1.0, y1 + 1.0])
    return rects


def normalize_rotated_pages(source: Path, target: Path) -> list[RotatedPage]:
    """把竖排整页转正，写到 ``target``（可与 ``source`` 同名）。没有这类页时不写文件，返回空列表。"""
    if not rotation_enabled() or not source.is_file():
        return []
    fitz = _import_fitz()
    doc = fitz.open(str(source))
    try:
        pages = detect_rotated_pages(doc)
        if not pages:
            return []
        records: list[RotatedPage] = []
        for index, cw in pages.items():
            page = doc[index]
            box = page.mediabox
            matrix, (new_w, new_h) = _matrix(cw, box)
            keep = _flat_line_rects(page)
            body = page.read_contents()
            prefix = ("q %s cm\n" % " ".join(f"{v:.6f}" for v in matrix)).encode("ascii")
            xref = doc.get_new_xref()
            doc.update_object(xref, "<<>>")
            doc.update_stream(xref, prefix + body + b"\nQ\n")
            page.set_contents(xref)
            new_box = fitz.Rect(0, 0, new_w, new_h)
            page.set_mediabox(new_box)
            page.set_cropbox(new_box)
            records.append(RotatedPage(index, cw, float(box.width), float(box.height), keep))
        tmp = target.with_suffix(target.suffix + ".rotmp")
        target.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(tmp), garbage=1, deflate=True)
        tmp.replace(target)
        return records
    finally:
        doc.close()


def write_sidecar(workdir: Path, origin: Path, records: list[RotatedPage]) -> None:
    sidecar = workdir / SIDECAR
    try:
        if records:
            workdir.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(
                json.dumps({"origin": str(origin), "records": [r.as_dict() for r in records]}, ensure_ascii=False),
                encoding="utf-8",
            )
        else:
            sidecar.unlink(missing_ok=True)
    except OSError:
        pass


def read_sidecar(workdir: Path) -> tuple[Path, list[RotatedPage]] | None:
    sidecar = workdir / SIDECAR
    if not sidecar.is_file():
        return None
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    return Path(data.get("origin") or ""), [RotatedPage(**item) for item in data.get("records", [])]


def _restore_flat_lines(fitz, page, origin_doc, rec: RotatedPage, *, dx: float) -> None:
    """页脚、页码在转正后被引擎丢弃：把原页对应区域原样盖回（先擦白，避免重影）。"""
    if origin_doc is None or not rec.keep or rec.page >= len(origin_doc):
        return
    for x0, y0, x1, y1 in rec.keep:
        clip = fitz.Rect(x0, y0, x1, y1)
        target = fitz.Rect(x0 + dx, y0, x1 + dx, y1)
        page.draw_rect(target, color=None, fill=(1, 1, 1), width=0)
        page.show_pdf_page(target, origin_doc, rec.page, clip=clip)


def finish_rotated_pages(pdf: Path, origin: Path, records: list[RotatedPage], *, dual: bool) -> dict[str, Any]:
    """译后把横版页转回原方向。整份文件失败时不改文件。"""
    summary: dict[str, Any] = {"restored": 0, "skipped": 0}
    if not rotation_enabled() or not records or not pdf.is_file():
        return summary
    fitz = _import_fitz()
    doc = fitz.open(str(pdf))
    src = fitz.open(str(pdf))
    origin_doc = fitz.open(str(origin)) if origin.is_file() else None
    try:
        for rec in sorted(records, key=lambda r: r.page):
            if rec.page >= len(doc):
                summary["skipped"] += 1
                continue
            before = len(doc)
            try:
                old_w, old_h = float(doc[rec.page].rect.width), float(doc[rec.page].rect.height)
                back = rec.cw  # show_pdf_page 的 rotate 为逆时针；逆时针转 cw 度正好抵消转正时的顺时针
                new_w, new_h = rec.width, rec.height
                if dual:
                    half = old_w / 2.0
                    page = doc.new_page(pno=rec.page, width=new_w * 2, height=new_h)
                    left = fitz.Rect(0, 0, new_w, new_h)
                    right = fitz.Rect(new_w, 0, new_w * 2, new_h)
                    if origin_doc is not None and rec.page < len(origin_doc):
                        page.show_pdf_page(left, origin_doc, rec.page)
                    page.show_pdf_page(
                        right, src, rec.page, clip=fitz.Rect(half, 0, half * 2, old_h), rotate=back
                    )
                    _restore_flat_lines(fitz, page, origin_doc, rec, dx=new_w)
                else:
                    page = doc.new_page(pno=rec.page, width=new_w, height=new_h)
                    page.show_pdf_page(fitz.Rect(0, 0, new_w, new_h), src, rec.page, rotate=back)
                    _restore_flat_lines(fitz, page, origin_doc, rec, dx=0.0)
                doc.delete_page(rec.page + 1)
                summary["restored"] += 1
            except Exception:  # noqa: BLE001
                if len(doc) > before:
                    doc.delete_page(rec.page)
                summary["skipped"] += 1
        if summary["restored"]:
            tmp = pdf.with_suffix(pdf.suffix + ".rotmp")
            doc.save(str(tmp), garbage=1, deflate=True)
            tmp.replace(pdf)
        return summary
    finally:
        if origin_doc is not None:
            origin_doc.close()
        src.close()
        doc.close()

# SPDX-License-Identifier: MPL-2.0
"""PLAN-027b/028a：文档内嵌图 Tier-1/3 结构扫描（stdlib + 可选 pymupdf/PIL）。"""
from __future__ import annotations

import hashlib
import io
import os
import time
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from qyunslation.structure.ingest import InputPreparationError, detect_input
from qyunslation.structure.models import SourceFormat


@dataclass
class PrescanCandidate:
    kind: str  # bitmap | emf | vector_region
    index: int
    display_width_pt: float = 0.0
    display_height_pt: float = 0.0
    page_frac: float | None = None
    is_header: bool = False
    page_no: int | None = None
    xref: int | None = None
    part_name: str | None = None
    occurrence_index: int | None = None
    reason_hint: str = "ok"


@dataclass
class Tier1Result:
    file_hash: str
    file_name: str
    file_type: str  # pdf | docx | image | unsupported | encrypted | corrupt
    candidate_count: int = 0
    emf_count: int = 0
    vector_count: int = 0
    frame_count: int = 0
    summary_text: str = ""
    candidates: list[PrescanCandidate] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class Tier3Result:
    vector_count: int = 0
    table_count: int = 0
    pages_scanned: int = 0
    truncated: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def file_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash the complete file; callers use this as a stable asset identity."""

    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _png_jpeg_size(data: bytes) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            return int(im.size[0]), int(im.size[1])
    except Exception:
        return 0, 0


def _px_to_pt_guess(w: int, h: int) -> tuple[float, float]:
    # 假设 96 DPI 显示估算
    return w * 72.0 / 96.0, h * 72.0 / 96.0


def _scan_ooxml_tier1(
    path: Path,
    *,
    file_type: str,
    media_prefix: str,
    max_candidates: int = 20,
) -> Tier1Result:
    name = path.name
    fh = file_sha256(path)
    try:
        z = zipfile.ZipFile(path)
    except Exception as exc:
        return Tier1Result(
            file_hash=fh,
            file_name=name,
            file_type="corrupt",
            summary_text="文档结构损坏，已禁用内嵌图翻译",
            error=str(exc),
        )
    cands: list[PrescanCandidate] = []
    emf = 0
    with z:
        media = [
            item
            for item in z.namelist()
            if item.startswith(media_prefix) and not item.endswith("/")
        ]
        for i, name_m in enumerate(sorted(media)):
            low = name_m.lower()
            if low.endswith((".emf", ".wmf")):
                emf += 1
                continue
            if not low.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")):
                continue
            try:
                data = z.read(name_m)
            except Exception:
                continue
            pw, ph = _png_jpeg_size(data)
            dw, dh = _px_to_pt_guess(pw, ph) if pw and ph else (0.0, 0.0)
            from qyunslation.extensions.doc_image_policy import evaluate_geometry

            ok, reason = evaluate_geometry(
                display_width_pt=dw,
                display_height_pt=dh,
                pixel_w=pw,
                pixel_h=ph,
            )
            if not ok:
                continue
            cands.append(
                PrescanCandidate(
                    kind="bitmap",
                    index=len(cands),
                    display_width_pt=dw,
                    display_height_pt=dh,
                    part_name=name_m,
                    occurrence_index=i + 1,
                    reason_hint=reason,
                )
            )
            if len(cands) >= max_candidates:
                break
    summary = f"检测到 {len(cands)} 处候选插图"
    if emf:
        summary += f"（另有 {emf} 处 EMF/WMF 矢量图，本期不翻）"
    summary += "，正在检测文本…" if cands else "。"
    return Tier1Result(
        file_hash=fh,
        file_name=name,
        file_type=file_type,
        candidate_count=len(cands),
        emf_count=emf,
        summary_text=summary,
        candidates=cands,
    )


def scan_docx_tier1(path: Path, *, max_candidates: int = 20) -> Tier1Result:
    return _scan_ooxml_tier1(
        path,
        file_type="docx",
        media_prefix="word/media/",
        max_candidates=max_candidates,
    )


def scan_pptx_tier1(path: Path, *, max_candidates: int = 20) -> Tier1Result:
    return _scan_ooxml_tier1(
        path,
        file_type="pptx",
        media_prefix="ppt/media/",
        max_candidates=max_candidates,
    )


def scan_pdf_tier1(path: Path, *, max_candidates: int = 20) -> Tier1Result:
    name = path.name
    fh = file_sha256(path)
    try:
        import pymupdf
    except ImportError:
        return Tier1Result(
            file_hash=fh,
            file_name=name,
            file_type="pdf",
            summary_text="缺少 pymupdf，无法预扫描 PDF 插图",
            error="pymupdf_missing",
        )
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        return Tier1Result(
            file_hash=fh,
            file_name=name,
            file_type="corrupt",
            summary_text="PDF 打开失败，已禁用内嵌图翻译",
            error=str(exc),
        )
    if getattr(doc, "is_encrypted", False) and not doc.authenticate(""):
        doc.close()
        return Tier1Result(
            file_hash=fh,
            file_name=name,
            file_type="encrypted",
            summary_text="文档受密码保护，已禁用内嵌图翻译",
            error="encrypted",
        )
    from qyunslation.extensions.doc_image_policy import evaluate_geometry

    cands: list[PrescanCandidate] = []
    seen_xref: set[int] = set()
    try:
        for pno in range(len(doc)):
            page = doc[pno]
            page_area = float(page.rect.width * page.rect.height) or 1.0
            infos = page.get_image_info(xrefs=True) or []
            for info in infos:
                xref = int(info.get("xref") or 0)
                if not xref or xref in seen_xref:
                    continue
                bbox = info.get("bbox")
                if not bbox:
                    continue
                x0, y0, x1, y1 = bbox
                dw, dh = float(x1 - x0), float(y1 - y0)
                frac = (dw * dh) / page_area
                ok, reason = evaluate_geometry(
                    display_width_pt=dw,
                    display_height_pt=dh,
                    page_frac=frac,
                )
                if not ok:
                    continue
                seen_xref.add(xref)
                cands.append(
                    PrescanCandidate(
                        kind="bitmap",
                        index=len(cands),
                        display_width_pt=dw,
                        display_height_pt=dh,
                        page_frac=frac,
                        page_no=pno + 1,
                        xref=xref,
                        reason_hint=reason,
                    )
                )
                if len(cands) >= max_candidates:
                    break
            if len(cands) >= max_candidates:
                break
    finally:
        doc.close()
    summary = f"检测到 {len(cands)} 处候选插图"
    summary += "，正在检测文本…" if cands else "。"
    return Tier1Result(
        file_hash=fh,
        file_name=name,
        file_type="pdf",
        candidate_count=len(cands),
        summary_text=summary,
        candidates=cands,
    )


def scan_image_tier1(path: Path) -> Tier1Result:
    fh = file_sha256(path)
    data = path.read_bytes()
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            pw, ph = map(int, image.size)
            frame_count = int(getattr(image, "n_frames", 1))
            image.verify()
    except Exception as exc:
        return Tier1Result(
            file_hash=fh,
            file_name=path.name,
            file_type="corrupt",
            summary_text="图片损坏或当前运行时无法解码",
            error=f"image_decode_failed:{type(exc).__name__}",
        )
    dw, dh = _px_to_pt_guess(pw, ph)
    from qyunslation.extensions.doc_image_policy import evaluate_geometry

    ok, reason = evaluate_geometry(display_width_pt=dw, display_height_pt=dh, pixel_w=pw, pixel_h=ph)
    cands = []
    if ok:
        cands = [
            PrescanCandidate(
                kind="bitmap",
                index=0,
                display_width_pt=dw,
                display_height_pt=dh,
                reason_hint=reason,
            )
        ]
    return Tier1Result(
        file_hash=fh,
        file_name=path.name,
        file_type="image",
        candidate_count=len(cands),
        frame_count=frame_count,
        summary_text=("检测到 1 处图片，正在检测文本…" if cands else "图片过小，跳过嵌字。"),
        candidates=cands,
    )


def scan_file_tier1(path: str | Path) -> Tier1Result:
    path = Path(path)
    if not path.is_file():
        return Tier1Result(
            file_hash="",
            file_name=path.name,
            file_type="unsupported",
            summary_text="文件不存在或不可读取",
            error="FILE_NOT_FOUND",
        )
    try:
        detected = detect_input(path.name, path.read_bytes())
    except InputPreparationError as exc:
        corrupt_codes = {"INVALID_CONTAINER", "FORMAT_CONTENT_INVALID"}
        return Tier1Result(
            file_hash=file_sha256(path),
            file_name=path.name,
            file_type="corrupt" if exc.code in corrupt_codes else "unsupported",
            summary_text=exc.message,
            error=exc.code,
        )

    source_format = detected.source_format
    if source_format is SourceFormat.DOCX:
        return scan_docx_tier1(path)
    if source_format is SourceFormat.PPTX:
        return scan_pptx_tier1(path)
    if source_format is SourceFormat.DOC:
        return Tier1Result(
            file_hash=file_sha256(path),
            file_name=path.name,
            file_type="normalize_docx",
            summary_text=".doc 需要先规范化为 .docx",
            error="normalization_required",
        )
    if source_format is SourceFormat.PPT:
        return Tier1Result(
            file_hash=file_sha256(path),
            file_name=path.name,
            file_type="normalize_pptx",
            summary_text=".ppt 需要先规范化为 .pptx",
            error="normalization_required",
        )
    if source_format is SourceFormat.PDF:
        return scan_pdf_tier1(path)
    if source_format in {
        SourceFormat.PNG,
        SourceFormat.JPEG,
        SourceFormat.WEBP,
        SourceFormat.BMP,
        SourceFormat.TIFF,
        SourceFormat.SVG,
        SourceFormat.GIF,
        SourceFormat.HEIF,
        SourceFormat.HEIC,
        SourceFormat.AVIF,
    }:
        return scan_image_tier1(path)
    return Tier1Result(
        file_hash=file_sha256(path),
        file_name=path.name,
        file_type="unsupported",
        summary_text="不支持的文件类型",
        error="unsupported",
    )


def scan_pdf_tier3(
    path: str | Path,
    *,
    max_pages: int | None = None,
    deadline_s: float | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> Tier3Result:
    """PLAN-028a：PDF 矢量插图 + 表格结构扫描（共享 find_tables 结果）。"""
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        return Tier3Result()

    max_pages = int(
        max_pages if max_pages is not None else os.environ.get("QYUNSLATION_PRESCAN_TIER3_MAX_PAGES", "40")
    )
    deadline_s = float(
        deadline_s if deadline_s is not None else os.environ.get("QYUNSLATION_PRESCAN_TIER3_DEADLINE", "25")
    )

    try:
        import pymupdf
    except ImportError:
        return Tier3Result(error="pymupdf_missing")

    try:
        from pdf_figure_crop import find_safe_vector_figures, table_rects
    except ImportError:
        return Tier3Result(error="pdf_figure_crop_missing")

    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        return Tier3Result(error=str(exc))

    if getattr(doc, "is_encrypted", False) and not doc.authenticate(""):
        doc.close()
        return Tier3Result(error="encrypted")

    started = time.monotonic()
    vector_count = 0
    table_count = 0
    pages_scanned = 0
    truncated = False

    try:
        total = len(doc)
        limit = min(total, max_pages)
        for pno in range(limit):
            if should_abort and should_abort():
                truncated = True
                break
            if time.monotonic() - started > deadline_s:
                truncated = True
                break
            page = doc[pno]
            tables = table_rects(page)
            table_count += len(tables)
            vector_count += len(find_safe_vector_figures(page, tables=tables))
            pages_scanned += 1
        if limit < total and pages_scanned >= limit:
            truncated = truncated or limit < total
    finally:
        doc.close()

    return Tier3Result(
        vector_count=vector_count,
        table_count=table_count,
        pages_scanned=pages_scanned,
        truncated=truncated,
    )


def format_tier3_summary(
    entry: dict,
    *,
    vector_count: int,
    table_count: int,
    truncated: bool = False,
    pages_scanned: int = 0,
) -> str:
    """PLAN-028a：合并 Tier-2 位图结论与 Tier-3 矢量/表格计数。"""
    bitmap_n = int(entry.get("candidate_count") or 0)
    translatable = int(entry.get("translatable_count") or 0)
    vector_n = int(vector_count or 0)
    table_n = int(table_count or 0)
    total_illust = bitmap_n + vector_n

    if total_illust == 0 and table_n == 0:
        text = "未检测到需要嵌字的插图。"
    elif total_illust == 0:
        text = f"未检测到需要嵌字的插图；另有 {table_n} 处表格，按文字层翻译。"
    elif bitmap_n and vector_n:
        text = (
            f"检测到 {total_illust} 处插图（{bitmap_n} 处位图、{vector_n} 处矢量图），"
            f"将随文档一并翻译"
        )
        if translatable and translatable < bitmap_n:
            text = (
                f"检测到 {total_illust} 处插图（{bitmap_n} 处位图、{vector_n} 处矢量图），"
                f"其中 {translatable} 处位图含待译文字，将随文档一并翻译"
            )
        if table_n:
            text += f"；另有 {table_n} 处表格，按文字层翻译"
        text += "。"
    elif vector_n:
        text = f"检测到 {vector_n} 处矢量插图，将随文档一并翻译"
        if table_n:
            text += f"；另有 {table_n} 处表格，按文字层翻译"
        text += "。"
    else:
        text = f"检测到 {bitmap_n} 处插图"
        if translatable:
            text += f"，其中 {translatable} 处含待译文字，将随文档一并翻译"
        elif bitmap_n:
            text += "，将随文档一并翻译"
        if table_n:
            text += f"；另有 {table_n} 处表格，按文字层翻译"
        text += "。"

    if truncated and pages_scanned:
        text = text.rstrip("。") + f"（仅扫描前 {pages_scanned} 页）。"
    return text


def format_tier2_summary(tier1, *, translatable: int, errors: int = 0) -> str:
    if isinstance(tier1, dict):
        n = int(tier1.get("candidate_count") or 0)
        emf = int(tier1.get("emf_count") or 0)
        summary = tier1.get("summary_text") or ""
    else:
        n = int(tier1.candidate_count)
        emf = int(tier1.emf_count)
        summary = tier1.summary_text
    if n == 0 and emf == 0:
        return summary.replace("，正在检测文本…", "。").rstrip("。") + "。"
    parts = [f"检测到 {n} 处插图"]
    if translatable:
        parts.append(f"其中 {translatable} 处含待译文字，将随文档一并翻译")
    else:
        parts.append("无可译文字（纯数字/已是目标语种），原样保留")
    if emf:
        parts.append(f"另有 {emf} 处 EMF/WMF 本期不翻")
    if errors:
        parts.append(f"{errors} 处检测失败，翻译时将重试")
    return "；".join(parts) + "。"

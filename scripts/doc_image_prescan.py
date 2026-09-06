# SPDX-License-Identifier: MPL-2.0
"""PLAN-027b：文档内嵌图 Tier-1 快速结构扫描（stdlib + 可选 pymupdf/PIL）。"""
from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


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
    reason_hint: str = "ok"


@dataclass
class Tier1Result:
    file_hash: str
    file_name: str
    file_type: str  # pdf | docx | image | unsupported | encrypted | corrupt
    candidate_count: int = 0
    emf_count: int = 0
    vector_count: int = 0
    summary_text: str = ""
    candidates: list[PrescanCandidate] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def file_sha256(path: Path, *, limit: int = 32 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        remaining = limit
        while remaining > 0:
            chunk = f.read(min(65536, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
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


def scan_docx_tier1(path: Path, *, max_candidates: int = 20) -> Tier1Result:
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
        media = [n for n in z.namelist() if n.startswith("word/media/") and not n.endswith("/")]
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
        file_type="docx",
        candidate_count=len(cands),
        emf_count=emf,
        summary_text=summary,
        candidates=cands,
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
    pw, ph = _png_jpeg_size(data)
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
        summary_text=("检测到 1 处图片，正在检测文本…" if cands else "图片过小，跳过嵌字。"),
        candidates=cands,
    )


def scan_file_tier1(path: str | Path) -> Tier1Result:
    path = Path(path)
    suf = path.suffix.lower()
    if suf in {".docx"}:
        return scan_docx_tier1(path)
    if suf == ".doc":
        return Tier1Result(
            file_hash=file_sha256(path),
            file_name=path.name,
            file_type="unsupported",
            summary_text=".doc 请另存为 .docx 后再做内嵌图翻译",
            error="doc_not_supported",
        )
    if suf == ".pdf":
        return scan_pdf_tier1(path)
    if suf in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return scan_image_tier1(path)
    return Tier1Result(
        file_hash=file_sha256(path) if path.is_file() else "",
        file_name=path.name,
        file_type="unsupported",
        summary_text="不支持的文件类型",
        error="unsupported",
    )


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

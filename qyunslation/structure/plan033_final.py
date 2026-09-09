# SPDX-License-Identifier: MPL-2.0
"""PLAN-033l：最终 mono/dual PDF 验收与补丁签名。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

PLAN033_SAMPLE_SHA256 = (
    "c88ea994746e13904ed012943130896426b8812f939ae14917e1c48f59b2f8dc"
)
EXPECTED_MODEL = "qwen3.6:35b-a3b"
EXPECTED_ENDPOINT = "http://100.67.66.123:11434/v1"


def resolve_sample() -> Path | None:
    override = os.environ.get("QYUNSLATION_PLAN033_SAMPLE", "").strip()
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates.extend(
        [
            Path("/home/dev/.hermes/attachments/1-s2.0-S2666636725013958-main.pdf"),
            Path(
                "/home/dev/pdf2zh/pdf2zh_files/"
                "d10bbff3-0701-431b-ad9e-9992f4f7792c/"
                "1-s2.0-S2666636725013958-main.pdf"
            ),
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def resolve_outputs() -> dict[str, Path | None]:
    mono = os.environ.get("QYUNSLATION_PLAN033_MONO", "").strip()
    dual = os.environ.get("QYUNSLATION_PLAN033_DUAL", "").strip()
    default_dir = Path(
        "/home/dev/pdf2zh/pdf2zh_files/a0de9853-5da9-4db3-a989-b74b0ab87d40"
    )
    return {
        "mono": Path(mono) if mono else _first_existing(
            default_dir / "1-s2.0-S2666636725013958-main.no_watermark.zh-CN.mono.pdf"
        ),
        "dual": Path(dual) if dual else _first_existing(
            default_dir / "1-s2.0-S2666636725013958-main.no_watermark.zh-CN.dual.pdf"
        ),
    }


def _first_existing(path: Path) -> Path | None:
    return path if path.is_file() else None


def page_hash(path: Path, page_index: int, *, x_min_frac: float = 0.0) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        page = doc[page_index]
        clip = page.rect
        if x_min_frac > 0:
            clip = pymupdf.Rect(clip.x0, clip.y0, clip.x0 + clip.width * x_min_frac, clip.y1)
        elif x_min_frac == 0 and False:
            pass
        pix = page.get_pixmap(clip=clip, dpi=72, alpha=False)
        return hashlib.sha256(pix.tobytes("png")).hexdigest()
    finally:
        doc.close()


def left_page_hash(path: Path, page_index: int) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        page = doc[page_index]
        clip = pymupdf.Rect(page.rect.x0, page.rect.y0, page.rect.x0 + page.rect.width * 0.5, page.rect.y1)
        pix = page.get_pixmap(clip=clip, dpi=72, alpha=False)
        return hashlib.sha256(pix.tobytes("png")).hexdigest()
    finally:
        doc.close()


def babeldoc_version() -> str:
    try:
        from importlib.metadata import version

        return version("babeldoc")
    except Exception:
        return ""


def patch_signature() -> dict[str, str]:
    site = Path(
        "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
    )
    files = {
        "il": site / "babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py",
        "terms": site / "babeldoc/format/pdf/document_il/midend/automatic_term_extractor.py",
        "creater": site / "babeldoc/format/pdf/document_il/frontend/il_creater.py",
        "fontmap": site / "babeldoc/format/pdf/document_il/utils/fontmap.py",
    }
    out = {}
    for name, path in files.items():
        if not path.is_file():
            out[name] = "missing"
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        marked = "033h" in text or "_QY_033H_PRESERVE" in text or "infer_bold" in text
        out[name] = f"{digest}:{int(marked)}"
    return out


def inspect_final() -> dict:
    sample = resolve_sample()
    outputs = resolve_outputs()
    report: dict = {
        "sample": str(sample) if sample else None,
        "mono": str(outputs["mono"]) if outputs["mono"] else None,
        "dual": str(outputs["dual"]) if outputs["dual"] else None,
        "blocked": [],
        "fail": [],
        "pass": [],
        "stats": {},
        "model_trace": None,
        "babeldoc": babeldoc_version(),
        "patch_signature": patch_signature(),
    }
    if sample is None:
        report["blocked"].append("SAMPLE_MISSING")
        return report
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    if digest != PLAN033_SAMPLE_SHA256:
        report["fail"].append(f"SAMPLE_HASH {digest}")
        return report
    from qyunslation.structure.scan_pdf import PdfStructureScanner
    from qyunslation.structure.models import ObjectType

    manifest = PdfStructureScanner().scan(sample)
    report["stats"]["figure_count"] = manifest.summary.figure_count
    report["stats"]["table_count"] = manifest.summary.table_count
    if manifest.summary.figure_count != 2:
        report["fail"].append(f"FIGURE_COUNT={manifest.summary.figure_count}")
    else:
        report["pass"].append("figure_count=2")
    if manifest.summary.table_count != 4:
        report["fail"].append(f"TABLE_COUNT={manifest.summary.table_count}")
    else:
        report["pass"].append("table_count=4")
    tables = [o for o in manifest.objects if o.type is ObjectType.TABLE]
    for table in tables:
        if not table.translatable_blocks:
            report["fail"].append(f"TABLE_BLOCKS_MISSING:{table.semantic_id}")
        if table.execution_status.value == "PENDING" and not table.translatable_blocks:
            report["fail"].append(f"TABLE_PENDING:{table.semantic_id}")
    if outputs["mono"] is None or outputs["dual"] is None:
        report["blocked"].append("FINAL_PDF_MISSING")
        return report
    import pymupdf

    dual = pymupdf.open(outputs["dual"])
    src = pymupdf.open(sample)
    try:
        pending_hits = 0
        for i, page in enumerate(dual):
            text = page.get_text() or ""
            if "PENDING" in text:
                pending_hits += 1
            if i < len(src):
                try:
                    left = left_page_hash(outputs["dual"], i)
                    orig = _full_page_hash(sample, i)
                    if left != orig:
                        report["fail"].append(f"DUAL_LEFT_MISMATCH:page{i+1}")
                        break
                except Exception as exc:
                    report["fail"].append(f"DUAL_LEFT_HASH_ERROR:{exc}")
                    break
        if pending_hits:
            report["fail"].append(f"PENDING_IN_PDF:{pending_hits}")
        else:
            report["pass"].append("no_pending_text")
        # 旧产物若仍翻译了 References 标题，记失败
        refs = "\n".join((dual[p].get_text() or "") for p in range(max(0, len(dual) - 3), len(dual)))
        if "参考文献" in refs and "References" not in refs:
            report["fail"].append("REFERENCES_HEADING_TRANSLATED")
    finally:
        dual.close()
        src.close()
    return report


def _full_page_hash(path: Path, page_index: int) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        pix = doc[page_index].get_pixmap(dpi=72, alpha=False)
        return hashlib.sha256(pix.tobytes("png")).hexdigest()
    finally:
        doc.close()

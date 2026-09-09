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
    if override:
        path = Path(override)
        return path if path.is_file() else None
    return None


def resolve_outputs() -> dict[str, Path | None]:
    mono = os.environ.get("QYUNSLATION_PLAN033_MONO", "").strip()
    dual = os.environ.get("QYUNSLATION_PLAN033_DUAL", "").strip()
    staging = Path("/tmp/plan033-staging")
    stem = "1-s2.0-S2666636725013958-main.no_watermark.zh"
    prod = Path("/home/dev/pdf2zh/pdf2zh_files/a0de9853-5da9-4db3-a989-b74b0ab87d40")
    candidates_mono = [
        Path(mono) if mono else None,
        staging / f"{stem}.mono.imgtr.tbltr.pdf",
        staging / f"{stem}.mono.imgtr.pdf",
        staging / f"{stem}.mono.pdf",
        prod / "1-s2.0-S2666636725013958-main.no_watermark.zh-CN.mono.pdf",
    ]
    candidates_dual = [
        Path(dual) if dual else None,
        staging / f"{stem}.dual.imgtr.tbltr.pdf",
        staging / f"{stem}.dual.imgtr.pdf",
        staging / f"{stem}.dual.pdf",
        prod / "1-s2.0-S2666636725013958-main.no_watermark.zh-CN.dual.pdf",
    ]
    return {
        "mono": next((p for p in candidates_mono if p is not None and p.is_file()), None),
        "dual": next((p for p in candidates_dual if p is not None and p.is_file()), None),
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


def _endpoint_matches(endpoint: str) -> bool:
    got = (endpoint or "").rstrip("/")
    want = EXPECTED_ENDPOINT.rstrip("/")
    return got == want or got.startswith(want) or want.startswith(got)


def attach_execution_assertions(report: dict, source_sha256: str, exe=None) -> None:
    """把执行 Manifest 的 model_trace / 对象终态并入 033l 总门。"""
    from qyunslation.structure.models import ExecutionStatus, ObjectType
    from qyunslation.structure.role_fitter import HARD_FAIL, QC_FONT_BELOW_TARGET

    if exe is None:
        from qyunslation.structure import ManifestStore

        exe = ManifestStore().get_execution(source_sha256)
    if exe is None:
        report["fail"].append("EXECUTION_MANIFEST_MISSING")
        return
    trace = dict((exe.extensions or {}).get("model_trace") or {})
    report["model_trace"] = trace
    if trace.get("model_id") == EXPECTED_MODEL and _endpoint_matches(
        str(trace.get("endpoint") or "")
    ):
        report["pass"].append("model_trace")
    else:
        report["fail"].append(f"MODEL_TRACE:{trace}")
    for obj in exe.objects:
        status = obj.execution_status
        if obj.type is ObjectType.TABLE:
            if not obj.translatable_blocks:
                report["fail"].append(f"TABLE_NO_BLOCKS:{obj.semantic_id}")
            elif status is ExecutionStatus.FAILED_HARD:
                report["fail"].append(f"TABLE_FAILED_HARD:{obj.semantic_id}:{obj.reason_code}")
            elif status is ExecutionStatus.TRANSLATED:
                report["pass"].append(f"table:{obj.semantic_id}")
            elif status is not ExecutionStatus.EXPLICITLY_SKIPPED:
                report["fail"].append(f"TABLE_STATUS:{obj.semantic_id}:{status}")
            continue
        if obj.type not in (ObjectType.FIGURE, ObjectType.IMAGE):
            continue
        checks = (obj.output_evidence.checks if obj.output_evidence else {}) or {}
        qc = list(checks.get("object_qc") or [])
        if any(code in HARD_FAIL for code in qc):
            report["fail"].append(f"FIGURE_QC_HARD:{obj.semantic_id}:{qc}")
        elif status is ExecutionStatus.TRANSLATED:
            report["pass"].append(f"figure:{obj.semantic_id}")
            if QC_FONT_BELOW_TARGET in qc and checks.get("dpi") not in (450, 600):
                report["fail"].append(f"FIGURE_DPI:{obj.semantic_id}:{checks.get('dpi')}")
        elif status is ExecutionStatus.EXPLICITLY_SKIPPED:
            continue
        else:
            report["fail"].append(f"FIGURE_STATUS:{obj.semantic_id}:{status}")


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
    attach_execution_assertions(report, digest)
    return report


def _full_page_hash(path: Path, page_index: int) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        pix = doc[page_index].get_pixmap(dpi=72, alpha=False)
        return hashlib.sha256(pix.tobytes("png")).hexdigest()
    finally:
        doc.close()

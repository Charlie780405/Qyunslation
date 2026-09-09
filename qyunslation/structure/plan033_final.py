# SPDX-License-Identifier: MPL-2.0
"""PLAN-033l / 033m：最终 mono/dual PDF 验收与补丁签名。

033m：产物必须绑定当前 HEAD；对输出 PDF 做内容探针，禁止旧 staging 冒充通过。
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

PLAN033_SAMPLE_SHA256 = (
    "c88ea994746e13904ed012943130896426b8812f939ae14917e1c48f59b2f8dc"
)
EXPECTED_MODEL = "qwen3.6:35b-a3b"
EXPECTED_ENDPOINT = "http://100.67.66.123:11434/v1"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_STEM = "1-s2.0-S2666636725013958-main.no_watermark.zh"
TABLE1_MIN_BODY_CELLS = 6
TABLE_MIN_BODY_CELLS = 4
TABLE1_MIN_REGION_CJK = 40
TABLE_MIN_REGION_CJK = 4


def repo_head_short() -> str:
    override = os.environ.get("QYUNSLATION_PLAN033_HEAD", "").strip()
    if override:
        return override
    try:
        out = subprocess.check_output(
            ["git", "-C", "/home/dev/qyunslation", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except Exception:
        return ""


def resolve_sample() -> Path | None:
    override = os.environ.get("QYUNSLATION_PLAN033_SAMPLE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    files_root = Path("/home/dev/pdf2zh/pdf2zh_files")
    for cand in files_root.glob(
        "*/1-s2.0-S2666636725013958-main.pdf"
    ):
        if cand.is_file():
            return cand
    return None


def head_staging_dir(head: str | None = None) -> Path | None:
    h = (head or repo_head_short()).strip()
    if not h:
        return None
    path = Path(f"/tmp/plan033m-{h}")
    return path if path.is_dir() else None


def resolve_outputs() -> dict[str, Path | None]:
    """优先 env / HEAD 绑定目录；旧 /tmp/plan033-staging 仅作 fallback 且须带 HEAD 标记。"""
    mono = os.environ.get("QYUNSLATION_PLAN033_MONO", "").strip()
    dual = os.environ.get("QYUNSLATION_PLAN033_DUAL", "").strip()
    head = repo_head_short()
    staging = head_staging_dir(head)
    legacy = Path("/tmp/plan033-staging")
    candidates_mono: list[Path | None] = [Path(mono) if mono else None]
    candidates_dual: list[Path | None] = [Path(dual) if dual else None]
    if staging is not None:
        for suffix in (".mono.imgtr.tbltr.pdf", ".mono.imgtr.pdf", ".mono.pdf"):
            candidates_mono.append(staging / f"{_STEM}{suffix}")
        for suffix in (".dual.imgtr.tbltr.pdf", ".dual.imgtr.pdf", ".dual.pdf"):
            candidates_dual.append(staging / f"{_STEM}{suffix}")
    # 旧目录：仅当 HEAD 文件匹配当前 HEAD 才接受
    legacy_head = legacy / "HEAD"
    if legacy.is_dir() and legacy_head.is_file() and legacy_head.read_text().strip() == head:
        for suffix in (".mono.imgtr.tbltr.pdf", ".mono.imgtr.pdf", ".mono.pdf"):
            candidates_mono.append(legacy / f"{_STEM}{suffix}")
        for suffix in (".dual.imgtr.tbltr.pdf", ".dual.imgtr.pdf", ".dual.pdf"):
            candidates_dual.append(legacy / f"{_STEM}{suffix}")
    return {
        "mono": next((p for p in candidates_mono if p is not None and p.is_file()), None),
        "dual": next((p for p in candidates_dual if p is not None and p.is_file()), None),
        "head": head,
        "staging": str(staging) if staging is not None else None,
    }


def left_page_hash(path: Path, page_index: int) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        page = doc[page_index]
        mid = page.rect.x0 + page.rect.width * 0.5
        clip = pymupdf.Rect(page.rect.x0, page.rect.y0, mid, page.rect.y1)
        pix = page.get_pixmap(clip=clip, dpi=72, alpha=False)
        return hashlib.sha256(pix.tobytes("png")).hexdigest()
    finally:
        doc.close()


def _full_page_hash(path: Path, page_index: int) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        pix = doc[page_index].get_pixmap(dpi=72, alpha=False)
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


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _table_body_blocks(table) -> list:
    return [
        block
        for block in (table.translatable_blocks or [])
        if str(getattr(block, "role", "") or "") != "table_title"
    ]


def assert_table_grids(report: dict, tables: list) -> None:
    """单元计数绿不能代替侧放/密表被压成 1–2 格。"""
    by_id = {getattr(table, "semantic_id", ""): table for table in tables}
    table1 = by_id.get("table:1")
    if table1 is None:
        report["fail"].append("TABLE1_MISSING")
    else:
        body = _table_body_blocks(table1)
        rows = {block.row_index for block in body}
        cols = {block.column_index for block in body}
        if len(body) < TABLE1_MIN_BODY_CELLS or (len(rows) < 3 and len(cols) < 3):
            report["fail"].append(f"TABLE1_COLLAPSED:{len(body)}r{len(rows)}c{len(cols)}")
        else:
            report["pass"].append(f"table1_cells={len(body)}")
    for semantic_id in ("table:2", "table:3", "table:4"):
        table = by_id.get(semantic_id)
        if table is None:
            report["fail"].append(f"TABLE_MISSING:{semantic_id}")
            continue
        body = _table_body_blocks(table)
        rows = {block.row_index for block in body}
        cols = {block.column_index for block in body}
        if len(body) < TABLE_MIN_BODY_CELLS or len(rows) < 2 or len(cols) < 2:
            report["fail"].append(
                f"TABLE_COLLAPSED:{semantic_id}:{len(body)}r{len(rows)}c{len(cols)}"
            )
        else:
            report["pass"].append(f"{semantic_id}_cells={len(body)}")


def _cjk_count(text: str) -> int:
    return len(_CJK_RE.findall(text or ""))


def attach_execution_assertions(report: dict, source_sha256: str, exe=None) -> None:
    """把执行 Manifest 的 model_trace / 对象终态并入总门。"""
    from qyunslation.structure.models import ExecutionStatus, ObjectType
    from qyunslation.structure.role_fitter import (
        HARD_FAIL,
        QC_FONT_BELOW_TARGET,
        QC_OVERFLOW,
        QC_ROLE_SIZE_DRIFT,
    )
    table_soft = {QC_FONT_BELOW_TARGET, QC_ROLE_SIZE_DRIFT, QC_OVERFLOW}

    if exe is None:
        from qyunslation.structure import ManifestStore

        exe = ManifestStore().get_execution(source_sha256)
    if exe is None:
        report["fail"].append("EXECUTION_MANIFEST_MISSING")
        return
    if not (exe.extensions or {}).get("terminal"):
        report["fail"].append("EXECUTION_NOT_TERMINAL")
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
        checks = (obj.output_evidence.checks if obj.output_evidence else {}) or {}
        if obj.type is ObjectType.TABLE:
            if not obj.translatable_blocks:
                report["fail"].append(f"TABLE_NO_BLOCKS:{obj.semantic_id}")
            elif status is ExecutionStatus.FAILED_HARD:
                report["fail"].append(
                    f"TABLE_FAILED_HARD:{obj.semantic_id}:{obj.reason_code}"
                )
            elif status is ExecutionStatus.TRANSLATED:
                report["pass"].append(f"table:{obj.semantic_id}")
                block_qc = checks.get("blocks") or {}
                hard = []
                for meta in block_qc.values() if isinstance(block_qc, dict) else []:
                    for code in list((meta or {}).get("qc") or []):
                        if code in HARD_FAIL and code not in table_soft:
                            hard.append(code)
                if hard:
                    report["fail"].append(f"TABLE_QC_HARD:{obj.semantic_id}:{hard}")
            elif status is not ExecutionStatus.EXPLICITLY_SKIPPED:
                report["fail"].append(f"TABLE_STATUS:{obj.semantic_id}:{status}")
            continue
        if obj.type not in (ObjectType.FIGURE, ObjectType.IMAGE):
            continue
        qc = list(checks.get("object_qc") or [])
        if any(code in HARD_FAIL for code in qc):
            report["fail"].append(f"FIGURE_QC_HARD:{obj.semantic_id}:{qc}")
        elif status is ExecutionStatus.TRANSLATED:
            report["pass"].append(f"figure:{obj.semantic_id}")
            if QC_FONT_BELOW_TARGET in qc and checks.get("dpi") not in (450, 600):
                report["fail"].append(
                    f"FIGURE_DPI:{obj.semantic_id}:{checks.get('dpi')}"
                )
        elif status is ExecutionStatus.EXPLICITLY_SKIPPED:
            continue
        else:
            report["fail"].append(f"FIGURE_STATUS:{obj.semantic_id}:{status}")


def _probe_table_regions(report: dict, mono_doc, tables: list) -> None:
    import pymupdf

    for table in tables:
        semantic_id = getattr(table, "semantic_id", "") or "table:?"
        try:
            page_no = int(str(table.canvas_id).split(":")[-1])
        except Exception:
            report["fail"].append(f"TABLE_PAGE_MISSING:{semantic_id}")
            continue
        index = page_no - 1
        if index < 0 or index >= len(mono_doc) or table.bbox is None:
            report["fail"].append(f"TABLE_PAGE_MISSING:{semantic_id}")
            continue
        box = table.bbox
        clip = pymupdf.Rect(box.x0, box.y0, box.x1, box.y1)
        text = mono_doc[index].get_text("text", clip=clip) or ""
        n_cjk = _cjk_count(text)
        need = TABLE1_MIN_REGION_CJK if semantic_id == "table:1" else TABLE_MIN_REGION_CJK
        if n_cjk < need:
            report["fail"].append(f"TABLE_REGION_NO_CJK:{semantic_id}:{n_cjk}")
        else:
            report["pass"].append(f"table_region_cjk:{semantic_id}={n_cjk}")


def _probe_output_pdf(report: dict, sample: Path, mono: Path, dual: Path, tables: list | None = None) -> None:
    """对输出 PDF 做内容级探针（不是只扫源 PDF）。"""
    import pymupdf

    dual_doc = pymupdf.open(dual)
    mono_doc = pymupdf.open(mono)
    src = pymupdf.open(sample)
    try:
        pending_hits = 0
        # 双语左侧：并排页宽约为原稿 2× 时比左半；交替模式比偶数页整页
        side_by_side = False
        if len(dual_doc) > 0 and len(src) > 0:
            side_by_side = dual_doc[0].rect.width >= src[0].rect.width * 1.5
        n_check = min(len(dual_doc), len(src) if side_by_side else len(dual_doc))
        for i in range(n_check):
            text = dual_doc[i].get_text() or ""
            if "PENDING" in text:
                pending_hits += 1
            try:
                if side_by_side:
                    if i >= len(src):
                        break
                    left = left_page_hash(dual, i)
                    orig = _full_page_hash(sample, i)
                else:
                    # 交替页：偶页（0-based）应为原稿
                    if i % 2 != 0:
                        continue
                    src_i = i // 2
                    if src_i >= len(src):
                        break
                    left = _full_page_hash(dual, i)
                    orig = _full_page_hash(sample, src_i)
                if left != orig:
                    report["fail"].append(f"DUAL_LEFT_MISMATCH:page{i + 1}")
            except Exception as exc:
                report["fail"].append(f"DUAL_LEFT_HASH_ERROR:{exc}")
        if pending_hits:
            report["fail"].append(f"PENDING_IN_PDF:{pending_hits}")
        else:
            report["pass"].append("no_pending_text")

        mono_text = "\n".join((mono_doc[p].get_text() or "") for p in range(len(mono_doc)))
        dual_all = "\n".join((dual_doc[p].get_text() or "") for p in range(len(dual_doc)))
        refs_pages = [
            dual_doc[p].get_text() or ""
            for p in range(len(dual_doc))
            if "REFERENCES" in (dual_doc[p].get_text() or "")
            or "References" in (dual_doc[p].get_text() or "")
        ]
        refs_text = "\n".join(refs_pages) or dual_all
        # 参考文献：标题不得被译成「参考文献」独占；条目应保留英文作者/DOI 痕迹
        if "参考文献" in refs_text and "References" not in refs_text and "REFERENCES" not in refs_text:
            report["fail"].append("REFERENCES_HEADING_TRANSLATED")
        else:
            report["pass"].append("references_heading_preserved")
        doi_hits = len(re.findall(r"10\.\d{4,9}/", refs_text))
        if doi_hits < 1:
            report["fail"].append("REFERENCES_DOI_MISSING")
        else:
            report["pass"].append(f"references_doi={doi_hits}")

        # 表题/单元格：mono 应出现中文「表」题注
        table_caption_hits = len(re.findall(r"表\s*[1-4]", mono_text))
        if table_caption_hits < 1:
            report["fail"].append(f"TABLE_CAPTION_CJK_MISSING:{table_caption_hits}")
        else:
            report["pass"].append(f"table_caption_cjk={table_caption_hits}")
        if not _has_cjk(mono_text):
            report["fail"].append("MONO_NO_CJK")
        else:
            report["pass"].append("mono_has_cjk")
        if tables:
            _probe_table_regions(report, mono_doc, tables)

        # 粗体抽样：源 PDF 有 Bold 字体名的 span，mono 同页也应有 bold/heavy 字体痕迹
        bold_ok = False
        for i in range(min(len(src), len(mono_doc), 6)):
            src_fonts = {
                (span.get("font") or "").lower()
                for block in (src[i].get_text("dict") or {}).get("blocks", [])
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            }
            if not any("bold" in f or f.endswith(".b") or "black" in f for f in src_fonts):
                continue
            mono_fonts = {
                (span.get("font") or "").lower()
                for block in (mono_doc[i].get_text("dict") or {}).get("blocks", [])
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            }
            if any(
                "bold" in f or f.endswith(".b") or "black" in f or "heavy" in f
                for f in mono_fonts
            ):
                bold_ok = True
                break
        if bold_ok:
            report["pass"].append("bold_heading_sample")
        else:
            report["fail"].append("BOLD_HEADING_LOST")
    finally:
        dual_doc.close()
        mono_doc.close()
        src.close()


def inspect_final() -> dict:
    sample = resolve_sample()
    outputs = resolve_outputs()
    report: dict = {
        "sample": str(sample) if sample else None,
        "mono": str(outputs["mono"]) if outputs["mono"] else None,
        "dual": str(outputs["dual"]) if outputs["dual"] else None,
        "head": outputs.get("head"),
        "staging": outputs.get("staging"),
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
    from qyunslation.structure.models import ObjectType
    from qyunslation.structure.scan_pdf import PdfStructureScanner

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
    assert_table_grids(report, tables)
    if outputs["mono"] is None or outputs["dual"] is None:
        report["blocked"].append("FINAL_PDF_MISSING")
        report["blocked"].append(
            f"NEED_HEAD_STAGING:/tmp/plan033m-{outputs.get('head') or 'HEAD'}"
        )
        return report
    # 拒绝未绑定 HEAD 的旧路径
    mono_s = str(outputs["mono"])
    if "/tmp/plan033-staging/" in mono_s and f"/tmp/plan033m-{outputs.get('head')}" not in mono_s:
        head_file = Path("/tmp/plan033-staging/HEAD")
        if not head_file.is_file() or head_file.read_text().strip() != outputs.get("head"):
            report["blocked"].append("STALE_STAGING_WITHOUT_HEAD")
            return report
    _probe_output_pdf(report, sample, outputs["mono"], outputs["dual"], tables)
    attach_execution_assertions(report, digest)
    return report

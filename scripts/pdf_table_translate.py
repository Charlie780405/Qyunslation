# SPDX-License-Identifier: MPL-2.0
"""PLAN-033j：生产路径表格翻译写出。"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
for path in (_SCRIPTS, _ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

logger = logging.getLogger(__name__)


def _llm_translator(to_lang: str):
    from qyunslation.extensions.image_translate import translate_texts

    cache_path = Path(
        os.environ.get(
            "QYUNSLATION_TABLE_TRANSLATE_CACHE",
            "/tmp/plan033m-table-zh-cache.json",
        )
    )
    cache: dict = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    def translate(payloads):
        out = {}
        missing = []
        for item in payloads:
            src = str(item["text"])
            hit = cache.get(item["id"])
            if isinstance(hit, dict) and hit.get("src") == src and str(hit.get("zh") or "").strip():
                out[item["id"]] = str(hit["zh"]).strip()
            else:
                missing.append(item)

        def _call_batch(items):
            if not items:
                return {}
            mapped = translate_texts([str(item["text"]) for item in items], to_lang=to_lang)
            got = {}
            for index, item in enumerate(items, start=1):
                zh = str(mapped.get(index) or "").strip()
                if zh:
                    got[item["id"]] = zh
            return got

        if missing:
            # PLAN-044b：禁止把源文静默当成译文；缺索引先整批再单条补译。
            got = _call_batch(missing)
            still = [item for item in missing if item["id"] not in got]
            for item in still:
                one = _call_batch([item])
                got.update(one)
            for item in missing:
                zh = got.get(item["id"], "")
                if zh:
                    cache[item["id"]] = {"src": str(item["text"]), "zh": zh}
                    out[item["id"]] = zh
                # 仍缺：不写入 out，由 translate_table_blocks / QC 记 MISSING_TARGET
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(cache, ensure_ascii=False), encoding="utf-8"
                )
            except OSError:
                pass
        return out

    return translate


def translate_pdf_tables(
    src: Path | str,
    *,
    origin: Path | str | None = None,
    to_lang: str = "简体中文",
    structure_manifest=None,
    x_min_frac: float | None = None,
    page_parity: str | None = None,
    translator=None,
) -> Path:
    """在 BabelDOC 译文 PDF 上按 Manifest 单元格重排矢量文字。"""
    import pymupdf

    from qyunslation.structure.execution_evidence import write_output_evidence
    from qyunslation.structure.models import ExecutionStatus, ObjectType
    from qyunslation.structure.role_fitter import fit_group
    from qyunslation.structure.scan_pdf import PdfStructureScanner
    from qyunslation.structure.table_qc import (
        assert_table_qc_clean,
        evaluate_table_qc,
        source_residue_on_page,
    )
    from qyunslation.structure.table_translate import TableTranslateError, translate_table_blocks
    from qyunslation.structure.table_writeback import (
        append_dual_continuation,
        append_mono_continuation,
        blocks_to_fit,
        paint_fitted_blocks,
        redact_source_blocks,
    )

    src_path = Path(src)
    origin_path = Path(origin) if origin else src_path
    if not src_path.is_file():
        return src_path
    manifest = structure_manifest
    if manifest is None:
        try:
            manifest = PdfStructureScanner().scan(origin_path)
        except Exception as exc:
            logger.warning("table scan failed: %s", exc)
            return src_path
    tables = sorted(
        [obj for obj in manifest.objects if obj.type is ObjectType.TABLE],
        key=lambda obj: (obj.semantic_id or "", int(obj.semantic_occurrence_index or 1)),
    )
    if not tables:
        return src_path
    from qyunslation.structure.models import ContentProfile

    profile = getattr(getattr(manifest, "document", None), "content_profile", None)
    profile_s = str(profile) if profile is not None else ""
    isolate_residue = profile is ContentProfile.REGULATORY or profile_s == "REGULATORY"
    literature = profile in {
        ContentProfile.RESEARCH_ARTICLE,
        ContentProfile.REVIEW_ARTICLE,
    } or profile_s in {"RESEARCH_ARTICLE", "REVIEW_ARTICLE"}
    if isolate_residue:
        table_size_mode = "ladder"
    elif literature:
        table_size_mode = "source_p75"
    else:
        table_size_mode = None
    normalize_table_sizes = table_size_mode is not None
    dest = src_path.with_name(src_path.stem + ".tbltr.pdf")
    doc = pymupdf.open(src_path)
    origin_doc = pymupdf.open(origin_path) if origin_path.is_file() else None
    try:
        worker = translator or _llm_translator(to_lang)
        changed = False
        touched = False
        failed = False
        for obj in tables:
            page_no = int(str(obj.canvas_id).split(":")[-1])
            page_index = page_no - 1
            if page_index < 0 or page_index >= len(doc):
                touched = True
                write_output_evidence(
                    obj, status=ExecutionStatus.FAILED_SOFT, reason_code="table_page_missing"
                )
                continue
            if page_parity == "even" and page_index % 2 != 0:
                continue
            if page_parity == "odd" and page_index % 2 != 1:
                continue
            touched = True
            blocks = list(obj.translatable_blocks or [])
            if not blocks:
                write_output_evidence(
                    obj, status=ExecutionStatus.EXPLICITLY_SKIPPED, reason_code="no_table_blocks"
                )
                continue
            try:
                translations = translate_table_blocks(blocks, worker)
                results = fit_group(
                    blocks_to_fit(blocks, translations),
                    normalize_table_sizes=normalize_table_sizes,
                    table_size_mode=table_size_mode,
                )
                records, hard = evaluate_table_qc(blocks, translations, results)
                assert_table_qc_clean(records, hard, isolate_residue=isolate_residue)
                redact_source_blocks(
                    doc[page_index],
                    blocks,
                    x_min_frac=x_min_frac,
                )
                _codes, title, header, leftover = paint_fitted_blocks(
                    doc[page_index],
                    blocks,
                    results,
                    x_min_frac=x_min_frac,
                )
                records, hard = evaluate_table_qc(
                    blocks, translations, results, leftover=leftover
                )
                hard.extend(
                    source_residue_on_page(
                        doc[page_index], blocks, translations, x_min_frac=x_min_frac
                    )
                )
                hard = list(dict.fromkeys(hard))
                assert_table_qc_clean(records, hard, isolate_residue=isolate_residue)
                if leftover:
                    if x_min_frac and origin_doc is not None:
                        append_dual_continuation(
                            doc,
                            origin_doc,
                            page_index,
                            title=title or obj.semantic_id or "表",
                            header=header,
                            rows=leftover,
                        )
                    else:
                        append_mono_continuation(
                            doc,
                            title=title or obj.semantic_id or "表",
                            header=header,
                            rows=leftover,
                        )
                block_checks = {record.block_id: record.as_dict() for record in records}
                write_output_evidence(
                    obj,
                    status=ExecutionStatus.TRANSLATED,
                    checks={
                        "digits_preserved": True,
                        "continuation_rows": len(leftover),
                        "blocks": block_checks,
                        "cells": [record.as_dict() for record in records],
                    },
                )
                changed = True
            except Exception as exc:
                failed = True
                logger.warning("table writeback failed %s: %s", obj.semantic_id, exc)
                message = str(exc)
                if "TABLE_DIGIT_DRIFT" in message:
                    reason_code = "table_digit_drift"
                elif "TABLE_" in message:
                    reason_code = "table_translate_failed"
                else:
                    reason_code = "table_writeback_failed"
                write_output_evidence(
                    obj,
                    status=ExecutionStatus.FAILED_HARD,
                    reason_code=reason_code,
                    checks={"error": message, "digits_preserved": False},
                )
        if touched:
            _persist(manifest, terminal_success=not failed)
        if not changed:
            return src_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(dest, garbage=3, deflate=True)
        return dest if dest.is_file() else src_path
    finally:
        doc.close()
        if origin_doc is not None:
            origin_doc.close()


def _persist(manifest, *, terminal_success: bool = True) -> None:
    try:
        from qyunslation.structure import ManifestStore
        from qyunslation.structure.execution_evidence import (
            merge_prior_execution,
            write_output_evidence,
        )
        from qyunslation.structure.model_trace import apply_current_model_trace
        from qyunslation.structure.models import ExecutionStatus, ObjectType

        merge_prior_execution(
            manifest, keep_types={ObjectType.FIGURE, ObjectType.IMAGE, ObjectType.TABLE}
        )
        for obj in manifest.objects:
            if obj.execution_status is ExecutionStatus.PENDING:
                write_output_evidence(
                    obj,
                    status=ExecutionStatus.EXPLICITLY_SKIPPED,
                    reason_code="not_reached",
                )
        try:
            from qyunslation.structure.table_execution_observability import (
                table_fidelity_payload,
            )

            manifest.extensions["table_fidelity"] = table_fidelity_payload(manifest)
        except Exception:
            pass
        manifest.extensions["terminal"] = True
        manifest.extensions["terminal_success"] = bool(terminal_success)
        manifest.refresh_summary()
        apply_current_model_trace(manifest)
        ManifestStore().put_execution(manifest)
    except Exception as exc:
        logger.warning("persist table execution failed: %s", exc)

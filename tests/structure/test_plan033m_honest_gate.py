# SPDX-License-Identifier: MPL-2.0
"""PLAN-033m：诚实总门与接线。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pymupdf

from qyunslation.structure import DocumentStructureManifest, PdfStructureScanner
from qyunslation.structure.models import BlockRole, BoundingBox, TranslatableBlock
from qyunslation.structure.plan033_final import (
    assert_table_grids,
    attach_execution_assertions,
    resolve_outputs,
)
from qyunslation.structure.references import is_section_break
from tests.structure.test_manifest_contract import SOURCE_SHA256, _minimal_manifest

ROOT = Path(__file__).resolve().parents[2]


def _load_docimg():
    path = ROOT / "scripts" / "apply-pdf2zh-docimg.py"
    spec = importlib.util.spec_from_file_location("apply_pdf2zh_docimg", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_docimg_refuses_soft_tbltr_swallow():
    docimg = _load_docimg()
    stale = '''
        # _qy_imgtr: PLAN-033c 原稿只读，嵌图改译文后处理
        if not state.get("_hpd_retried"):
            state["_pre_imgtr_origin_path"] = str(file_path)
        async for event in do_translate_async_stream(settings, file_path):
            pass
            # _qy_imgtr_post
            try:
                from pdf_image_translate import translate_pdf_images as _qy_tr_pdf_img
                def _qy_run_imgtr():
                    out_mono, out_dual = _mono, _dual
                    try:
                        from pdf_table_translate import translate_pdf_tables as _qy_tbltr
                        out_mono = str(_qy_tbltr(_qy_Pimg(out_mono)))
                    except Exception as _qy_tbl_exc:
                        import logging as _qy_tbl_log
                        _qy_tbl_log.getLogger(__name__).warning(
                            "表格写出跳过: %s", _qy_tbl_exc
                        )
                    return out_mono, out_dual
                _mono, _dual = await _qy_img_task
            except Exception as _qy_img_exc:
                import logging as _qy_img_log
                _qy_img_log.getLogger(__name__).warning(
                    "译文插图翻译跳过: %s", _qy_img_exc
                )
            result_entry = {
                "ok": True,
            }
'''
    updated, changed = docimg.upgrade_post_if_stale(stale)
    assert changed
    assert "表格写出跳过" not in updated
    assert "译文插图翻译跳过" not in updated
    assert "bind_task_model_trace" in updated
    assert "raise" in updated


def test_execution_requires_terminal_flag():
    payload = _minimal_manifest()
    payload["objects"][0]["execution_status"] = "TRANSLATED"
    payload["objects"][0]["output_evidence"] = {
        "checks": {"object_qc": [], "dpi": 300},
        "blocks": [],
    }
    payload["extensions"] = {
        "model_trace": {
            "model_id": "qwen3.6:35b-a3b",
            "endpoint": "http://100.67.66.123:11434/v1",
        }
    }
    exe = DocumentStructureManifest.model_validate(payload)
    report: dict = {"fail": [], "pass": [], "model_trace": None}
    attach_execution_assertions(report, SOURCE_SHA256, exe=exe)
    assert "EXECUTION_NOT_TERMINAL" in report["fail"]


def test_legacy_staging_without_head_not_preferred(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_PLAN033_HEAD", "deadbeef")
    monkeypatch.delenv("QYUNSLATION_PLAN033_MONO", raising=False)
    monkeypatch.delenv("QYUNSLATION_PLAN033_DUAL", raising=False)
    out = resolve_outputs()
    assert out["mono"] is None or "plan033m-deadbeef" in str(out["mono"])


class _FakeTable:
    def __init__(self, semantic_id: str, blocks: list[TranslatableBlock]):
        self.semantic_id = semantic_id
        self.translatable_blocks = blocks


def _cell(block_id: str, text: str, row: int, col: int, role: str = "table_cell") -> TranslatableBlock:
    return TranslatableBlock(
        block_id=block_id,
        source_text=text,
        bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10),
        role=role,
        row_index=row,
        column_index=col,
    )


def test_merge_prior_keeps_figure_when_table_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_MANIFEST_CACHE", str(tmp_path))
    from qyunslation.structure.execution_evidence import (
        merge_prior_execution,
        write_output_evidence,
    )
    from qyunslation.structure.models import ExecutionStatus, ObjectType

    current = DocumentStructureManifest.model_validate(_minimal_manifest())
    prior = DocumentStructureManifest.model_validate(_minimal_manifest())
    fig = next(o for o in prior.objects if o.type is ObjectType.FIGURE)
    write_output_evidence(fig, status=ExecutionStatus.TRANSLATED, checks={"dpi": 600})
    prior.extensions["kind"] = "execution"
    prior.extensions["terminal"] = True
    prior.refresh_summary()
    from qyunslation.structure import ManifestStore

    written = ManifestStore().put_execution(prior)
    assert written is not None
    merge_prior_execution(current, keep_types={ObjectType.FIGURE, ObjectType.IMAGE})
    got = next(o for o in current.objects if o.type is ObjectType.FIGURE)
    assert got.execution_status is ExecutionStatus.TRANSLATED


def test_inspect_rejects_collapsed_table_grids():
    report: dict = {"fail": [], "pass": []}
    tables = [
        _FakeTable("table:1", [_cell("table:1:title", "Table 1", 0, 0, BlockRole.TABLE_TITLE.value), _cell("table:1:r1c0", "all english", 1, 0, "table_header")]),
        _FakeTable("table:2", [_cell("table:2:r1c0", "row", 1, 0)]),
        _FakeTable("table:3", [_cell("table:3:r1c0", "row", 1, 0)]),
        _FakeTable("table:4", [_cell("table:4:r1c0", "row", 1, 0)]),
    ]
    assert_table_grids(report, tables)
    assert any(item.startswith("TABLE1_COLLAPSED") for item in report["fail"])
    assert any(item.startswith("TABLE_COLLAPSED:table:2") for item in report["fail"])


def test_scan_resets_references_after_appendix(tmp_path):
    path = tmp_path / "refs-appendix.pdf"
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_textbox(
        pymupdf.Rect(72, 72, 500, 200),
        "Body see [12] for details. MedImmune staff attended the kickoff meeting.",
    )
    p2 = doc.new_page()
    p2.insert_textbox(pymupdf.Rect(72, 72, 500, 100), "References")
    p2.insert_textbox(
        pymupdf.Rect(72, 110, 500, 160),
        "[12] Smith J. IQVIA report on biologics manufacturing. 2024.",
    )
    p2.insert_textbox(pymupdf.Rect(72, 180, 500, 210), "Appendix")
    p2.insert_textbox(
        pymupdf.Rect(72, 220, 500, 320),
        "Extra appendix body GenScend notes continue with more clinical detail for readers.",
    )
    doc.save(path)
    doc.close()
    assert is_section_break("Appendix")
    manifest = PdfStructureScanner().scan(path)
    bodies = [
        (o.translatable_blocks[0].source_text if o.translatable_blocks else "", o)
        for o in manifest.objects
        if o.type.value == "BODY"
    ]
    assert bodies, "expected body objects"
    appendix_body = next(o for t, o in bodies if "GenScend" in t)
    assert appendix_body.semantic_scope == "body"
    assert appendix_body.planned_action != "skip"
    assert appendix_body.reason_code != "reference_entry"

# SPDX-License-Identifier: MPL-2.0
"""PLAN-062f：表格后处理进度回调与真实图/表计数。"""
from pathlib import Path

from qyunslation.structure.progress import format_from_execution, format_semantic_progress


def test_table_translate_accepts_progress_cb():
    text = Path("scripts/pdf_table_translate.py").read_text(encoding="utf-8")
    assert "progress_cb=None" in text
    assert "progress_cb(index, len(tables))" in text


def test_docimg_splits_imgtr_and_tbltr_ranges():
    text = Path("scripts/apply-pdf2zh-docimg.py").read_text(encoding="utf-8")
    assert "0.92 + 0.04" in text
    assert "0.96 + 0.03" in text
    assert "progress_cb=_qy_tbl_progress" in text


def test_format_from_execution_counts_non_pending(monkeypatch):
    class _Obj:
        def __init__(self, kind, status):
            self.type = type("T", (), {"name": kind})()
            self.execution_status = type("S", (), {"name": status})()

    manifest = type("M", (), {"objects": [_Obj("FIGURE", "DONE"), _Obj("FIGURE", "PENDING"), _Obj("TABLE", "FAILED_SOFT")]})()
    assert format_from_execution(manifest) == format_semantic_progress(1, 2, 1, 1)

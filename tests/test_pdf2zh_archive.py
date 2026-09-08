# SPDX-License-Identifier: MPL-2.0
from pathlib import Path

import pytest

from qyunslation.archive.filenames import (
    original_filename_from_product,
    strip_pipeline_markers,
)
from qyunslation.archive.index_db import ArchiveIndex
from qyunslation.archive.pdf2zh_ingest import (
    infer_original_filename,
    ingest_pdf2zh_group,
    output_group_key,
)
from qyunslation.archive.storage import LocalStorageBackend


def test_output_group_key():
    assert output_group_key("page1.no_watermark.zh.mono.pdf") == "page1"
    assert output_group_key("page1.no_watermark.zh.dual.pdf") == "page1"
    assert output_group_key("readme.txt") is None


def test_infer_original_filename():
    assert infer_original_filename("page1.no_watermark.zh") == "page1.pdf"
    assert infer_original_filename("page1") == "page1.pdf"


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("page1.no_watermark.zh", "page1"),
        ("FDA responses on PIND.hpd-ocr", "FDA responses on PIND"),
        ("41467_2024_Article_53384.imgtr", "41467_2024_Article_53384"),
        # 多层叠加，顺序不定
        ("report.imgtr.hpd-ocr.no_watermark.zh", "report"),
        ("report.hpd-ocr.imgtr", "report"),
        ("方案设计图-20260728.zh", "方案设计图-20260728"),
        ("QX027N-201-CSP V1.3_translated", "QX027N-201-CSP V1.3"),
        # 未知后缀与版本号不得被剥
        ("annual_report.v2", "annual_report.v2"),
        ("study.final", "study.final"),
        ("plain", "plain"),
    ],
)
def test_strip_pipeline_markers(stem, expected):
    assert strip_pipeline_markers(stem) == expected


def test_strip_pipeline_markers_is_idempotent():
    once = strip_pipeline_markers("report.imgtr.no_watermark.zh")
    assert strip_pipeline_markers(once) == once


def test_original_filename_from_product_keeps_extension():
    assert original_filename_from_product("方案设计图-20260728.zh.jpg") == "方案设计图-20260728.jpg"
    assert original_filename_from_product("QX027N_translated.docx") == "QX027N.docx"
    assert original_filename_from_product("clean.docx") == "clean.docx"


def test_ingest_pdf2zh_group_local(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    mono = out_dir / "demo.no_watermark.zh.mono.pdf"
    dual = out_dir / "demo.no_watermark.zh.dual.pdf"
    mono.write_bytes(b"%PDF-mono")
    dual.write_bytes(b"%PDF-dual")

    storage = LocalStorageBackend(tmp_path / "objects")
    index = ArchiveIndex(tmp_path / "index.db")
    record = ingest_pdf2zh_group(
        storage=storage,
        index=index,
        group_key="demo.no_watermark.zh",
        paths=[mono, dual],
    )
    assert record.workflow_type == "pdf2zh"
    assert record.original_filename == "demo.pdf"
    assert len(record.files) == 2
    listed, total = index.list_records()
    assert total == 1
    assert listed[0].archive_id == record.archive_id

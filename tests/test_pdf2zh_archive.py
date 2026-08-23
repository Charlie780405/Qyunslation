# SPDX-License-Identifier: MPL-2.0
from pathlib import Path

from qyunslation.archive.index_db import ArchiveIndex
from qyunslation.archive.pdf2zh_ingest import (
    infer_original_filename,
    ingest_pdf2zh_group,
    output_group_key,
)
from qyunslation.archive.storage import LocalStorageBackend


def test_output_group_key():
    assert output_group_key("page1.no_watermark.zh.mono.pdf") == "page1.no_watermark.zh"
    assert output_group_key("page1.no_watermark.zh.dual.pdf") == "page1.no_watermark.zh"
    assert output_group_key("readme.txt") is None


def test_infer_original_filename():
    assert infer_original_filename("page1.no_watermark.zh") == "page1.pdf"


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

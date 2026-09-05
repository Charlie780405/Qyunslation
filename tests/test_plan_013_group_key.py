# SPDX-License-Identifier: MPL-2.0
from pathlib import Path

from qyunslation.archive.pdf2zh_ingest import (
    classify_output_file,
    normalize_group_stem,
    output_group_key,
)


def test_normalize_strips_hpd_and_lang():
    assert normalize_group_stem("FDA.hpd-ocr.zh-CN") == "FDA"
    assert normalize_group_stem("page1.no_watermark.zh") == "page1"
    assert normalize_group_stem("Abstract.hpd-ocr") == "Abstract"


def test_output_group_key_variants():
    assert output_group_key("x.hpd-ocr.letter-mono.pdf") == "x"
    assert output_group_key("x.no_watermark.zh.mono.pdf") == "x"
    assert output_group_key("x.zh.md") == "x"
    assert output_group_key("x.zh.docx") == "x"
    assert output_group_key("all_translations.zip") is None


def test_classify():
    assert classify_output_file(Path("a.letter-mono.pdf")) == "letter_mono_pdf"
    assert classify_output_file(Path("a.zh.md")) == "translated_md"
    assert classify_output_file(Path("doc.pdf"), group_key="doc") == "source_pdf"

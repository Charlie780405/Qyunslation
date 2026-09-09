"""PLAN-033j：表格翻译完整性、占位保护与续页。"""
from __future__ import annotations

import pytest

from qyunslation.structure.models import BlockRole, TranslatableBlock
from qyunslation.structure.protect import protect_tokens, restore_tokens
from qyunslation.structure.table_translate import (
    TableTranslateError,
    assert_vector_searchable,
    plan_dual_continuations,
    plan_mono_continuations,
    translate_table_blocks,
)


def _block(block_id: str, text: str, role=BlockRole.TABLE_CELL) -> TranslatableBlock:
    return TranslatableBlock(block_id=block_id, source_text=text, role=role)


def test_placeholders_keep_doi_url_and_percent():
    text = "IGA 0/1 was 42% (see [12]); DOI 10.1000/xyz https://doi.org/10.1000/xyz"
    protected, mapping = protect_tokens(text)
    assert "42%" not in protected
    assert "10.1000/xyz" not in protected
    assert "https://" not in protected
    assert restore_tokens(protected, mapping) == text


def test_incomplete_llm_payload_is_hard_fail():
    blocks = [_block("t1:r0c0", "Endpoint"), _block("t1:r0c1", "Value")]

    def translator(payloads):
        return {"t1:r0c0": "终点"}

    with pytest.raises(TableTranslateError, match="TABLE_LLM_INCOMPLETE"):
        translate_table_blocks(blocks, translator)


def test_missing_footnote_is_hard_fail():
    blocks = [
        _block("t1:r0c0", "Age"),
        _block("t1:fn0", "* Missing data excluded.", BlockRole.TABLE_FOOTNOTE),
    ]

    def translator(payloads):
        return {"t1:r0c0": "年龄"}

    with pytest.raises(TableTranslateError, match="TABLE_FOOTNOTE_MISSING|TABLE_LLM_INCOMPLETE"):
        translate_table_blocks(blocks, translator)


def test_mono_continuation_repeats_title_and_header():
    pages = plan_mono_continuations(
        table_number=2,
        title="表 2 应答率",
        header=["组别", "第16周"],
        rows=[["A", "1"], ["B", "2"], ["C", "3"]],
        rows_per_page=2,
    )
    assert pages[0].heading() == "表 2 应答率"
    assert pages[1].is_continuation
    assert pages[1].heading() == "表 2（续）"
    assert pages[1].header_texts == ["组别", "第16周"]


def test_dual_continuation_repeats_source_left_page():
    pages = plan_dual_continuations(source_page=5, continuation_count=2)
    assert [p.left_source_page for p in pages] == [5, 5, 5]
    assert pages[0].right_is_continuation is False
    assert pages[1].right_is_continuation is True


def test_searchable_text_required():
    with pytest.raises(TableTranslateError, match="TABLE_TEXT_NOT_SEARCHABLE"):
        assert_vector_searchable("only vector outlines", ["终点"])

"""PLAN-035a/035b：表格单元格数字 policy 与译后断言。"""
from __future__ import annotations

import pytest

from qyunslation.structure.models import BlockRole, TranslationPolicy, TranslatableBlock
from qyunslation.structure.table_cell_policy import (
    assert_digit_tokens_preserved,
    classify_cell_policy,
    is_preserve_cell,
)
from qyunslation.structure.table_translate import TableTranslateError, translate_table_blocks


def test_pure_numeric_cells_are_preserve():
    assert is_preserve_cell("42")
    assert is_preserve_cell("42.3%")
    assert is_preserve_cell("N/A")
    assert classify_cell_policy("42.3%") is TranslationPolicy.PRESERVE


def test_mixed_cells_use_protect_tokens():
    assert classify_cell_policy("Response 42%") is TranslationPolicy.PROTECT_TOKENS
    assert classify_cell_policy("Endpoint") is TranslationPolicy.TRANSLATE


def test_preserve_cells_skip_llm():
    blocks = [
        TranslatableBlock(
            block_id="t1:r0c0",
            source_text="Endpoint",
            role=BlockRole.TABLE_HEADER,
            translation_policy=TranslationPolicy.TRANSLATE,
        ),
        TranslatableBlock(
            block_id="t1:r1c1",
            source_text="42.3%",
            role=BlockRole.TABLE_CELL,
            translation_policy=TranslationPolicy.PRESERVE,
        ),
    ]

    def translator(payloads):
        assert len(payloads) == 1
        assert payloads[0]["id"] == "t1:r0c0"
        return {"t1:r0c0": "终点"}

    out = translate_table_blocks(blocks, translator)
    assert out["t1:r1c1"] == "42.3%"


def test_digit_drift_is_hard_fail():
    blocks = [
        TranslatableBlock(
            block_id="t1:r0c0",
            source_text="Rate 42%",
            role=BlockRole.TABLE_CELL,
            translation_policy=TranslationPolicy.PROTECT_TOKENS,
        )
    ]

    def translator(payloads):
        return {"t1:r0c0": "比率 99%"}

    with pytest.raises(TableTranslateError, match="TABLE_DIGIT_DRIFT"):
        translate_table_blocks(blocks, translator)


def test_assert_digit_tokens_preserved_accepts_restored():
    assert_digit_tokens_preserved("n = 120 (42%)", "n = 120 (42%)")

"""PLAN-043：042b 写回、词表、表格链软门与受控实体。"""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from qyunslation.glossary.governance import build_merged_dict
from qyunslation.structure.regulatory_entities import (
    lookup_controlled,
    normalize_phase_label,
    translate_or_preserve,
)
from qyunslation.structure.table_qc import TABLE_QC_SOFT, assert_table_qc_clean
from qyunslation.structure.table_translate import translate_table_blocks
from qyunslation.structure.models import (
    BoundingBox,
    TranslatableBlock,
    TranslationPolicy,
)


def test_form_glossary_043b_entries():
    m = build_merged_dict()
    assert m.get("药物名称") == "Drug Name"
    assert m.get("适应症") == "Indication"
    assert m.get("周清红") == "Zhou Qinghong"
    assert m.get("II期") == "Phase II"
    assert m.get("1、试验目的") == "1. Trial Objectives"


def test_phase_compact_variant():
    assert normalize_phase_label("II期") == "Phase II"


def test_person_name_uses_glossary_not_preserve():
    m = build_merged_dict()
    assert translate_or_preserve("周清红", mapping=m) == "Zhou Qinghong"
    assert translate_or_preserve("未知名", mapping=m) == "未知名"


def test_042b_patcher_requires_post_translate():
    path = Path(__file__).resolve().parents[2] / "scripts/apply-pdf2zh-042b-short-label.py"
    spec = spec_from_file_location("apply042b", path)
    mod = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    sample = (
        "logger = logging.getLogger(__name__)\n"
        "def process_page(self):\n"
        "        for paragraph in page.pdf_paragraph:\n"
        "            if len(paragraph.unicode) < "
        "self.translation_config.min_text_length:\n"
        "                continue\n"
    )
    patched, changed = mod.patch_il(sample)
    assert changed
    assert "post_translate_paragraph" in patched
    assert "set_paragraph_translated" not in patched
    assert "_qy_para_idx" in patched


def test_table_qc_soft_excludes_font_below():
    assert "FONT_BELOW_TARGET" in TABLE_QC_SOFT
    assert_table_qc_clean([], ["FONT_BELOW_TARGET"])
    # PLAN-044c：isolate 下单格 SOURCE_RESIDUE 不阻断；非 isolate 仍硬失败
    assert_table_qc_clean([], ["SOURCE_RESIDUE"], isolate_residue=True)
    try:
        assert_table_qc_clean([], ["SOURCE_RESIDUE"], isolate_residue=False)
        assert False, "non-isolate SOURCE_RESIDUE must remain hard"
    except Exception as exc:
        assert "SOURCE_RESIDUE" in str(exc)


def test_protect_tokens_fallback_on_drift():
    blocks = [
        TranslatableBlock(
            block_id="ctr",
            source_text="CTR20231233",
            translation_policy=TranslationPolicy.PROTECT_TOKENS,
            role="table_cell",
            row_index=0,
            column_index=1,
            bbox=BoundingBox(x0=0, y0=0, x1=80, y1=12),
        )
    ]

    def bad_llm(_payloads):
        return {"ctr": "WRONG"}

    out = translate_table_blocks(blocks, bad_llm)
    assert out["ctr"] == "CTR20231233"


def test_controlled_short_label_table_block():
    blocks = [
        TranslatableBlock(
            block_id="lbl",
            source_text="登记号",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            row_index=0,
            column_index=0,
            bbox=BoundingBox(x0=0, y0=0, x1=40, y1=12),
        )
    ]

    def boom(_payloads):
        raise AssertionError("LLM must not run")

    out = translate_table_blocks(blocks, boom)
    assert out["lbl"] == "Registration No."

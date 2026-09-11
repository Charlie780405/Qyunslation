"""PLAN-042：台账夹具、短标签、断词、归属、实体、告警交付。"""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from qyunslation.glossary.governance import (
    LAYER_PRIORITY,
    build_merged_dict,
    load_curated_entries,
    load_glossary_csv,
)
from qyunslation.structure.models import (
    BoundingBox,
    ExecutionStatus,
    ObjectType,
    OutputEvidence,
    TranslatableBlock,
    TranslationPolicy,
)
from qyunslation.structure.page_qc import QC_WORD_SPLIT, scan_page_text_qc
from qyunslation.structure.regulatory_entities import (
    lookup_controlled,
    normalize_phase_label,
    translate_or_preserve,
)
from qyunslation.structure.table_attribution import (
    QC_CELL_MERGE,
    QC_KEY_VALUE_COLLAPSE,
    evaluate_attribution,
)
from qyunslation.structure.table_execution_observability import execution_table_fidelity_hint
from qyunslation.structure.table_qc import evaluate_table_qc
from qyunslation.structure.table_translate import translate_table_blocks
from tests.structure.plan042_fixtures import (
    institution_form,
    key_value_form,
    section_number_samples,
    short_label_form,
    word_break_pressure_text,
)


def test_taxonomy_file_lists_24_classes():
    root = Path(__file__).resolve().parents[2]
    text = (
        root / "docs/plans/PLAN-042-regulatory-translation-quality/error-taxonomy.md"
    ).read_text(encoding="utf-8")
    ids = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) > 2 and cols[1][:1] in "ABCDEFG" and cols[1][1:2].isdigit():
            ids.append(cols[1])
    assert len(ids) >= 24


def test_short_label_fixture_builds(tmp_path):
    path = short_label_form(tmp_path / "short.pdf")
    assert path.is_file() and path.stat().st_size > 200


def test_form_layer_priority_and_short_value_lookup():
    assert LAYER_PRIORITY["form"] == 90
    assert LAYER_PRIORITY["org"] > LAYER_PRIORITY["form"] > LAYER_PRIORITY["clinical"]
    entries = load_curated_entries()
    assert any(e.layer == "form" for e in entries)
    mapping = build_merged_dict()
    assert mapping.get("双盲") == "Double-blind"
    assert mapping.get("进行中") == "Ongoing"
    assert mapping.get("登记号") == "Registration No."


def test_section_numbers_unique_and_controlled():
    mapping = build_merged_dict()
    seen_targets = []
    for src, expected in section_number_samples():
        hit = lookup_controlled(src, mapping=mapping)
        assert hit == expected, (src, hit, expected)
        seen_targets.append(hit)
    assert len(seen_targets) == len(set(seen_targets))


def test_phase_roman_not_eleven():
    assert normalize_phase_label("II 期") == "Phase II"
    assert normalize_phase_label("Ⅱ 期") == "Phase II"
    assert normalize_phase_label("11 期") == "Phase II"
    assert normalize_phase_label("III 期") == "Phase III"


def test_org_entity_3sbio_and_hospital():
    mapping = build_merged_dict()
    assert "3SBio" in lookup_controlled(
        "三生国健药业（上海）股份有限公司", mapping=mapping
    )
    assert "Tongren" in lookup_controlled(
        "首都医科大学附属北京同仁医院", mapping=mapping
    )
    assert (
        translate_or_preserve("未知偏远县人民医院", mapping=mapping)
        == "未知偏远县人民医院"
    )


def test_translate_table_blocks_uses_controlled_without_llm():
    blocks = [
        TranslatableBlock(
            block_id="b1",
            source_text="双盲",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            row_index=0,
            column_index=1,
            bbox=BoundingBox(x0=0, y0=0, x1=40, y1=12),
        ),
        TranslatableBlock(
            block_id="b2",
            source_text="II 期",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            row_index=1,
            column_index=1,
            bbox=BoundingBox(x0=0, y0=12, x1=40, y1=24),
        ),
    ]

    def boom(_payloads):
        raise AssertionError("LLM must not be called for controlled cells")

    out = translate_table_blocks(blocks, boom)
    assert out["b1"] == "Double-blind"
    assert out["b2"] == "Phase II"


def test_cell_merge_and_key_value_collapse_detected():
    blocks = [
        TranslatableBlock(
            block_id="inst",
            source_text="北京医院",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            row_index=1,
            column_index=1,
            bbox=BoundingBox(x0=0, y0=0, x1=120, y1=20),
        ),
        TranslatableBlock(
            block_id="person",
            source_text="杨弋",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            row_index=1,
            column_index=2,
            bbox=BoundingBox(x0=120, y0=0, x1=180, y1=20),
        ),
        TranslatableBlock(
            block_id="mail",
            source_text="a@b.com",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            row_index=2,
            column_index=1,
            bbox=BoundingBox(x0=0, y0=20, x1=120, y1=40),
        ),
    ]
    translations = {
        "inst": "Beijing Hospital Yang Yi",
        "person": "Yang Yi",
        "mail": "a@b.com Mailing Address",
    }
    issues = evaluate_attribution(blocks, translations)
    codes = {i.code for i in issues}
    assert QC_CELL_MERGE in codes
    assert QC_KEY_VALUE_COLLAPSE in codes


def test_evaluate_table_qc_surfaces_attribution_codes():
    blocks = [
        TranslatableBlock(
            block_id="inst",
            source_text="北京医院",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            row_index=0,
            column_index=0,
            bbox=BoundingBox(x0=0, y0=0, x1=100, y1=16),
        ),
        TranslatableBlock(
            block_id="person",
            source_text="李四",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            row_index=0,
            column_index=1,
            bbox=BoundingBox(x0=100, y0=0, x1=140, y1=16),
        ),
    ]
    translations = {"inst": "Beijing Hospital 李四", "person": "Li Si"}
    _records, hard = evaluate_table_qc(blocks, translations)
    assert "CELL_MERGE" in hard or "SOURCE_RESIDUE" in hard


def test_word_break_pressure_phrases_intact():
    for phrase in word_break_pressure_text():
        assert "sc ore" not in phrase
        assert "Mono-Long" not in phrase
        parts = phrase.split()
        assert all(len(p) >= 2 for p in parts)


def test_page_qc_detects_word_split(tmp_path):
    import pymupdf

    path = tmp_path / "split.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "immunogenicity sc ore indicator", fontsize=10)
    doc.save(path)
    doc.close()
    doc = pymupdf.open(path)
    try:
        result = scan_page_text_qc(doc[0], expect_target_lang="en", max_cjk_when_en=999)
    finally:
        doc.close()
    assert QC_WORD_SPLIT in result.qc
    assert any("sc ore" in h for h in result.word_split_hits)


def test_execution_hint_warns_on_failed_tables():
    from types import SimpleNamespace

    from qyunslation.structure.models import Representation, TableObject

    manifest = SimpleNamespace(
        issues=[],
        extensions={"terminal_success": False},
        objects=[
            TableObject.model_construct(
                type=ObjectType.TABLE,
                object_id="obj:" + "c" * 64,
                canvas_id="page:1",
                representation=Representation.NATIVE_TEXT,
                semantic_id="table:9",
                execution_status=ExecutionStatus.FAILED_HARD,
                reason_code="table_translate_failed",
                output_evidence=OutputEvidence(checks={"error": "TABLE_QC_HARD"}),
                translatable_blocks=[],
            )
        ],
    )
    hint = execution_table_fidelity_hint(manifest)
    assert "未保真" in hint
    assert "✗" in hint


def test_042b_patcher_injects_marker():
    path = Path(__file__).resolve().parents[2] / "scripts/apply-pdf2zh-042b-short-label.py"
    spec = spec_from_file_location("apply042b", path)
    mod = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    sample = (
        "logger = logging.getLogger(__name__)\n"
        "def process_page(self):\n"
        "            if len(paragraph.unicode) < "
        "self.translation_config.min_text_length:\n"
        "                continue\n"
    )
    patched, changed = mod.patch_il(sample)
    assert changed
    assert mod.MARKER in patched
    assert "_qy_direct" in patched


def test_key_value_and_institution_fixtures(tmp_path):
    assert key_value_form(tmp_path / "kv.pdf").is_file()
    assert institution_form(tmp_path / "inst.pdf").is_file()


def test_regulatory_form_fields_csv_loads():
    root = Path(__file__).resolve().parents[2]
    path = root / "glossaries/regulatory-form-fields.csv"
    rows = load_glossary_csv(path, default_layer="form")
    assert len(rows) >= 40
    assert all(r.layer == "form" for r in rows)


def test_patch_regulatory_typesetting_callable():
    import sys

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import doc_profile

    # May return False if babeldoc missing in test venv; function must exist.
    assert callable(doc_profile.patch_regulatory_typesetting)

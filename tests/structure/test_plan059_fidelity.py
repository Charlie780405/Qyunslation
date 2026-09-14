"""PLAN-059：结构计数、引用隔离、派生图片和表格保真契约。"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from qyunslation.structure.models import (
    BlockRole,
    ObjectType,
    SourceStyle,
    TranslatableBlock,
    TranslationPolicy,
)
from qyunslation.structure.references import (
    ReferenceProtectionError,
    is_reference_heading,
    mask_reference_sections,
    restore_reference_sections,
)
from qyunslation.structure.scan_pdf import PdfStructureScanner
from qyunslation.structure.table_translate import translate_table_blocks
from qyunslation.structure.table_writeback import blocks_to_fit
from qyunslation.ui.manifest_view import summarize_for_ui


ROOT = Path(__file__).resolve().parents[2]
LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"


def test_ljae_semantic_counts_are_not_physical_image_counts():
    manifest = PdfStructureScanner().scan(LJAE)

    assert manifest.summary.figure_count == 5
    assert manifest.summary.table_count == 3
    assert manifest.extensions["semantic_figure_count"] == 5
    assert manifest.extensions["table_count"] == 3
    assert manifest.extensions["physical_image_count"] >= 0
    assert manifest.extensions["physical_image_occurrence_count"] >= 0
    assert manifest.summary.occurrence_count == sum(
        item.type in {ObjectType.FIGURE, ObjectType.TABLE}
        for item in manifest.objects
    )
    view = summarize_for_ui(manifest.model_dump(mode="json"))
    assert view["figure_count"] == 5
    assert view["table_count"] == 3
    assert view["physical_image_count"] == manifest.summary.physical_image_count


def test_reference_mask_includes_heading_article_titles_and_metadata():
    source = (
        "# Results\n"
        "The result is significant.\n"
        "# References\n"
        "1. Smith J. Original article title. Journal 2024;1:1-8.\n"
        "2. Doe A. 中文文章标题。期刊 2025。 https://doi.org/10.1000/x\n"
        "# Appendix\n"
        "Supplementary methods.\n"
    )
    masked, sections = mask_reference_sections(source)

    assert "Original article title" not in masked
    assert "中文文章标题" not in masked
    assert "https://doi.org/10.1000/x" not in masked
    assert "# References" not in masked
    assert "# Appendix" in masked
    assert restore_reference_sections(masked, sections, strict=True) == source


def test_reference_mask_fails_closed_when_model_drops_sentinel():
    masked, sections = mask_reference_sections("Body\nReferences\n1. Article title.\n")
    assert sections
    with pytest.raises(ReferenceProtectionError, match="REFERENCE_SENTINEL_MISSING"):
        restore_reference_sections(masked.replace(next(iter(sections)), ""), sections, strict=True)


def test_table_footnote_is_translated_even_if_preserve_hint_is_present():
    footnote = TranslatableBlock(
        block_id="table:1:footnote:1",
        source_text="* Missing data were excluded from the analysis.",
        role=BlockRole.TABLE_FOOTNOTE,
        translation_policy=TranslationPolicy.PRESERVE,
    )
    called: list[list[dict]] = []

    def translator(payloads):
        called.append(payloads)
        return {payload["id"]: "* 分析中排除了缺失数据。" for payload in payloads}

    output = translate_table_blocks([footnote], translator)
    assert called and called[0][0]["id"] == footnote.block_id
    assert output[footnote.block_id] == "* 分析中排除了缺失数据。"


def test_table_source_bold_is_carried_into_fit_contract():
    block = TranslatableBlock(
        block_id="table:1:r0c0",
        source_text="Primary endpoint",
        role=BlockRole.TABLE_HEADER,
        source_style=SourceStyle(font_size=9.0, font_weight="bold"),
    )
    fitted = blocks_to_fit([block], {block.block_id: "主要终点"})
    assert fitted[0].source_bold is True
    assert fitted[0].source_size == 9.0


def test_master_dpi_is_written_to_derived_bytes_without_mutating_source():
    from qyunslation.extensions.doc_image_policy import ensure_master_dpi

    original = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(original, format="PNG")
    source = original.getvalue()
    source_hash = hashlib.sha256(source).hexdigest()
    derived = ensure_master_dpi(source, target_dpi=300)

    assert hashlib.sha256(source).hexdigest() == source_hash
    with Image.open(io.BytesIO(derived)) as image:
        assert image.info["dpi"][0] == pytest.approx(300, abs=1)
        assert image.info["dpi"][1] == pytest.approx(300, abs=1)
        assert image.size == (120, 80)


def test_reference_section_heading_supports_markdown_heading_form():
    assert is_reference_heading("## References:")


def test_model_trace_records_declared_qwen_and_embedding_route_without_live_claim():
    from qyunslation.structure.model_trace import (
        EXPECTED_EMBEDDING_MODEL,
        EXPECTED_TRANSLATION_MODEL,
        bind_task_model_trace,
        _CURRENT_TRACE,
    )

    token = _CURRENT_TRACE.set(None)
    try:
        trace = bind_task_model_trace(
            model_id=EXPECTED_TRANSLATION_MODEL,
            endpoint="http://100.67.66.123:11434/v1",
            extras={
                "provider": "qwen_ollama",
                "embedding_model": EXPECTED_EMBEDDING_MODEL,
                "embedding_endpoint": "http://100.67.66.123:11434/",
                "embedding_status": "configured",
                "target_lang": "简体中文",
                "termbase_version": "058-test",
            },
        )
    finally:
        _CURRENT_TRACE.reset(token)

    assert trace["model_id"] == EXPECTED_TRANSLATION_MODEL
    assert trace["embedding_model"] == EXPECTED_EMBEDDING_MODEL
    assert trace["embedding_status"] == "configured"
    assert trace["embedding_endpoint"] == "http://100.67.66.123:11434/"
    assert "token=" not in str(trace)


def test_markdown_agent_restores_reference_section_after_model_response():
    from qyunslation.agents.markdown_agent import MDTranslateAgent, MDTranslateAgentConfig

    source = "Body text.\n# References\n1. Author. Original title. Journal 2024.\n"
    masked, sections = mask_reference_sections(source)
    agent = MDTranslateAgent(
        MDTranslateAgentConfig(
            base_url="http://127.0.0.1:1/v1",
            model_id="test-model",
            to_lang="简体中文",
        )
    )
    assert agent._restore_results([source], [sections], [masked]) == [source]
    # A model that changes the sentinel must not be allowed to emit a mixed,
    # partially translated citation block.
    token = next(iter(sections))
    assert agent._restore_results([source], [sections], [masked.replace(token, "引用")]) == [source]

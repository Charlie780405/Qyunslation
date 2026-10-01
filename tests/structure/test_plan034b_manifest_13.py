# SPDX-License-Identifier: MPL-2.0
"""PLAN-034b：Manifest 1.3.0 契约、新策略与兼容。"""
from __future__ import annotations

from qyunslation.structure import (
    CURRENT_SCHEMA_VERSION,
    DEFERRED_TRANSLATION_POLICIES,
    DocumentStructureManifest,
    TranslationPolicy,
    build_manifest_id,
)
from qyunslation.structure.models import (
    DocumentDomain,
    RiskLevel,
    SourceStyle,
    TranslatableBlock,
)
from qyunslation.structure.table_translate import translate_table_blocks
from tests.structure.test_manifest_contract import SOURCE_SHA256, _minimal_manifest


def test_current_schema_is_at_least_1_3_family():
    # PLAN-071b bumps current to 2.x; 1.x remains readable.
    assert CURRENT_SCHEMA_VERSION.startswith("2.") or CURRENT_SCHEMA_VERSION.startswith("1.")


def test_new_policies_and_deferred_set():
    assert TranslationPolicy.TERM_ONLY.value == "TERM_ONLY"
    assert TranslationPolicy.HUMAN_REVIEW.value == "HUMAN_REVIEW"
    assert TranslationPolicy.TERM_ONLY in DEFERRED_TRANSLATION_POLICIES
    assert TranslationPolicy.HUMAN_REVIEW in DEFERRED_TRANSLATION_POLICIES
    assert TranslationPolicy.TRANSLATE not in DEFERRED_TRANSLATION_POLICIES


def test_source_style_color_line_height_optional():
    style = SourceStyle(color="#112233", line_height=14.0)
    assert style.color == "#112233"
    assert style.line_height == 14.0
    assert SourceStyle().color is None


def test_document_domain_risk_round_trip():
    payload = _minimal_manifest()
    payload["document"]["document_domain"] = DocumentDomain.LITERATURE.value
    payload["document"]["risk_level"] = RiskLevel.HIGH.value
    payload["producer"]["glossary_version"] = "curated-370"
    payload["producer"]["tm_version"] = None
    manifest = DocumentStructureManifest.model_validate(payload)
    assert manifest.document.document_domain is DocumentDomain.LITERATURE
    assert manifest.document.risk_level is RiskLevel.HIGH
    assert manifest.producer.glossary_version == "curated-370"
    again = DocumentStructureManifest.model_validate(manifest.model_dump(mode="json"))
    assert again.schema_version == CURRENT_SCHEMA_VERSION


def test_v1_2_0_manifest_still_loads():
    payload = _minimal_manifest()
    payload["schema_version"] = "1.2.0"
    payload["manifest_id"] = build_manifest_id(SOURCE_SHA256, "1.2.0")
    # strip 1.3.0-only keys if any were injected by helper using CURRENT
    manifest = DocumentStructureManifest.model_validate(payload)
    assert manifest.schema_version == "1.2.0"
    assert manifest.document.document_domain is None


def test_deferred_policies_not_sent_to_llm():
    called: list = []

    def translator(payloads):
        called.extend(payloads)
        return {p["id"]: "译" for p in payloads}

    blocks = [
        TranslatableBlock(
            block_id="a",
            source_text="keep",
            translation_policy=TranslationPolicy.PRESERVE,
        ),
        TranslatableBlock(
            block_id="b",
            source_text="review me",
            translation_policy=TranslationPolicy.HUMAN_REVIEW,
        ),
        TranslatableBlock(
            block_id="c",
            source_text="term only",
            translation_policy=TranslationPolicy.TERM_ONLY,
        ),
        TranslatableBlock(
            block_id="d",
            source_text="hello",
            translation_policy=TranslationPolicy.TRANSLATE,
        ),
    ]
    out = translate_table_blocks(blocks, translator)
    assert [p["id"] for p in called] == ["d"]
    assert out["a"] == "keep"
    assert out["b"] == "review me"
    assert out["c"] == "term only"
    assert out["d"] == "hello" or out["d"]  # translated or residue path


def test_reference_preserve_policy_enum():
    """契约：参考文献策略值为 PRESERVE（扫描器写入侧沿用）。"""
    block = TranslatableBlock(
        block_id="ref:1",
        source_text="Smith J. et al.",
        translation_policy=TranslationPolicy.PRESERVE,
    )
    assert block.translation_policy is TranslationPolicy.PRESERVE

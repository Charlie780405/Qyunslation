"""Executable evidence for PLAN-030 gaps that later child plans must close."""

from __future__ import annotations

from pathlib import Path

import pytest

from qyunslation.ir.document import Document
from qyunslation.server.core import get_workflow_type_from_filename
from qyunslation.translator.ai_translator.pptx_translator import (
    PPTXTranslator,
    PPTXTranslatorConfig,
)
from scripts.doc_image_prescan import format_tier3_summary, scan_file_tier1


def expected_gap(issue_code: str, owner: str, description: str):
    return pytest.mark.xfail(
        strict=True,
        reason=f"{issue_code} owner={owner}: {description}",
    )


@expected_gap(
    "QY030-SEM-001",
    "PLAN-030b",
    "physical bitmap/vector regions are still summed as user-facing figures",
)
def test_user_summary_reports_ljae439_semantic_figures_not_physical_regions():
    summary = format_tier3_summary(
        {"candidate_count": 5, "translatable_count": 5},
        vector_count=2,
        table_count=3,
    )

    assert "检测到 5 处插图" in summary
    assert "3 处表格" in summary
    assert "7 处插图" not in summary


@expected_gap(
    "QY030-FMT-001",
    "PLAN-030c",
    "TIFF is a core format contract but the current prescanner rejects it",
)
def test_core_tiff_is_accepted_by_the_shared_prescan_route(
    generated_structure_fixtures: Path,
):
    result = scan_file_tier1(generated_structure_fixtures / "multipage.tiff")

    assert result.file_type == "image"
    assert result.error is None


@expected_gap(
    "QY030-FMT-002",
    "PLAN-030c",
    "unknown binary suffixes still silently fall back to the text workflow",
)
def test_unknown_binary_format_fails_explicitly_instead_of_becoming_text():
    route = get_workflow_type_from_filename("opaque-payload.unknown")

    assert route != "txt"


@expected_gap(
    "QY030-NORM-001",
    "PLAN-030c",
    "legacy PPT is routed directly to a workflow that only accepts PPTX",
)
def test_legacy_ppt_routes_through_explicit_normalization():
    route = get_workflow_type_from_filename("legacy-deck.ppt")

    assert route != "pptx"


@expected_gap(
    "QY030-PPT-001",
    "PLAN-030f",
    "PPTX picture shapes have no translatable image object or execution state",
)
def test_pptx_picture_shape_is_emitted_as_a_translatable_object(
    generated_structure_fixtures: Path,
):
    source = generated_structure_fixtures / "presentation.pptx"
    document = Document.from_bytes(source.read_bytes(), suffix=".pptx", stem=source.stem)
    translator = PPTXTranslator(PPTXTranslatorConfig(skip_translate=True))

    _, elements, _ = translator._pre_translate(document)
    pictures = [item for item in elements if item.get("type") == "image"]

    assert len(pictures) == 1
    assert pictures[0]["execution_status"] == "PENDING"


@expected_gap(
    "QY030-PPT-002",
    "PLAN-030f",
    "PPTX is absent from the shared structure prescan despite being core",
)
def test_core_pptx_is_accepted_by_the_shared_prescan_route(
    generated_structure_fixtures: Path,
):
    result = scan_file_tier1(generated_structure_fixtures / "presentation.pptx")

    assert result.file_type == "pptx"
    assert result.error is None

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from qyunslation.converter.office import OfficeConversion
from qyunslation.structure.capabilities import RuntimeFeature, RuntimeState
from qyunslation.structure.ingest import (
    InputPreparationError,
    PreparedDocument,
    prepare_document,
    workflow_for_source_format,
)
from qyunslation.structure.models import AssetRole, ProcessingMode, SourceFormat
from qyunslation.structure.runtime import FeatureProbe, RuntimeCapabilitySnapshot


def _snapshot(*, missing: set[RuntimeFeature] | None = None) -> RuntimeCapabilitySnapshot:
    unavailable = missing or set()
    return RuntimeCapabilitySnapshot(
        probes=[
            FeatureProbe(
                feature=feature,
                available=feature not in unavailable,
                detail="test",
            )
            for feature in RuntimeFeature
        ]
    )


class FakeOfficeConverter:
    def __init__(self, fixture_path: Path, target: SourceFormat):
        self.fixture_path = fixture_path
        self.target = target

    def convert(self, source_name: str, content: bytes, source_format: SourceFormat):
        suffix = ".docx" if self.target is SourceFormat.DOCX else ".pptx"
        return OfficeConversion(
            output_name=f"{Path(source_name).stem}{suffix}",
            output_format=self.target,
            content=self.fixture_path.read_bytes(),
            converter="fake-office",
            converter_version="1.2.3",
            parameters={"target": suffix.removeprefix(".")},
        )


def test_prepares_core_pdf_without_fake_conversion_lineage(
    generated_structure_fixtures: Path,
):
    content = (generated_structure_fixtures / "single-column.pdf").read_bytes()

    prepared = prepare_document(
        "paper.pdf",
        content,
        declared_mime="application/pdf",
        requested_mode=ProcessingMode.NATIVE,
        runtime_snapshot=_snapshot(),
    )

    assert isinstance(prepared, PreparedDocument)
    assert prepared.source_format is SourceFormat.PDF
    assert prepared.normalized_format is SourceFormat.PDF
    assert prepared.source_sha256 == hashlib.sha256(content).hexdigest()
    assert prepared.normalized_sha256 == prepared.source_sha256
    assert prepared.content == content
    assert prepared.input_asset.role is AssetRole.INPUT
    assert prepared.derived_assets == ()
    assert prepared.conversion_lineage == ()
    assert len(prepared.canvases) == 1
    assert prepared.workflow_type == "markdown_based"
    assert prepared.capability.runtime_state is RuntimeState.AVAILABLE


@pytest.mark.parametrize(
    ("fixture_name", "source_format", "workflow_type", "canvas_count"),
    [
        ("multipage.tiff", SourceFormat.TIFF, "image_overlay", 2),
        ("presentation.pptx", SourceFormat.PPTX, "pptx", 1),
        ("review.docx", SourceFormat.DOCX, "docx", 1),
    ],
)
def test_prepares_other_core_formats(
    generated_structure_fixtures: Path,
    fixture_name: str,
    source_format: SourceFormat,
    workflow_type: str,
    canvas_count: int,
):
    content = (generated_structure_fixtures / fixture_name).read_bytes()

    prepared = prepare_document(
        fixture_name,
        content,
        runtime_snapshot=_snapshot(),
    )

    assert prepared.source_format is source_format
    assert prepared.workflow_type == workflow_type
    assert len(prepared.canvases) == canvas_count


@pytest.mark.parametrize(
    ("source_name", "source_format", "fixture_name", "target_format", "workflow_type"),
    [
        ("legacy.doc", SourceFormat.DOC, "review.docx", SourceFormat.DOCX, "docx"),
        ("legacy.ppt", SourceFormat.PPT, "presentation.pptx", SourceFormat.PPTX, "pptx"),
    ],
)
def test_prepares_legacy_office_with_hash_linked_lineage(
    generated_structure_fixtures: Path,
    source_name: str,
    source_format: SourceFormat,
    fixture_name: str,
    target_format: SourceFormat,
    workflow_type: str,
):
    source = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy"
    converter = FakeOfficeConverter(
        generated_structure_fixtures / fixture_name,
        target_format,
    )

    prepared = prepare_document(
        source_name,
        source,
        runtime_snapshot=_snapshot(),
        office_converter=converter,
    )

    assert prepared.source_format is source_format
    assert prepared.normalized_format is target_format
    assert prepared.workflow_type == workflow_type
    assert prepared.input_asset.sha256 == hashlib.sha256(source).hexdigest()
    assert len(prepared.derived_assets) == 1
    assert prepared.derived_assets[0].role is AssetRole.NORMALIZED
    assert prepared.derived_assets[0].sha256 == prepared.normalized_sha256
    assert len(prepared.conversion_lineage) == 1
    step = prepared.conversion_lineage[0]
    assert step.source_asset_id == prepared.input_asset.asset_id
    assert step.output_asset_id == prepared.derived_assets[0].asset_id
    assert step.converter == "fake-office"
    assert step.converter_version == "1.2.3"


def test_unavailable_requested_mode_fails_before_canvas_extraction(
    generated_structure_fixtures: Path,
):
    content = (generated_structure_fixtures / "single-column.pdf").read_bytes()

    with pytest.raises(InputPreparationError) as exc_info:
        prepare_document(
            "paper.pdf",
            content,
            requested_mode=ProcessingMode.HYBRID,
            runtime_snapshot=_snapshot(
                missing={RuntimeFeature.IMAGE_DECODER, RuntimeFeature.OCR_ENGINE}
            ),
        )

    assert exc_info.value.code == "RUNTIME_CAPABILITY_UNAVAILABLE"


def test_prepared_document_repr_and_audit_do_not_expose_content(
    generated_structure_fixtures: Path,
):
    content = (generated_structure_fixtures / "single-column.pdf").read_bytes()
    prepared = prepare_document(
        "private-paper.pdf",
        content,
        runtime_snapshot=_snapshot(),
    )

    audit = prepared.audit_dict()
    assert "content" not in audit
    assert content[:30].decode("latin-1") not in repr(prepared)
    assert audit["source_sha256"] == hashlib.sha256(content).hexdigest()
    assert audit["canvas_count"] == 1


def test_workflow_mapping_is_explicit_and_unknown_fails():
    assert workflow_for_source_format(SourceFormat.PDF) == "markdown_based"
    assert workflow_for_source_format(SourceFormat.DOCX) == "docx"
    assert workflow_for_source_format(SourceFormat.PNG) == "image_overlay"
    assert workflow_for_source_format(SourceFormat.PPTX) == "pptx"

    with pytest.raises(InputPreparationError) as exc_info:
        workflow_for_source_format(SourceFormat.UNKNOWN)
    assert exc_info.value.code == "WORKFLOW_ROUTE_UNSUPPORTED"

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure.canvases import CanvasLimits, extract_canvases
from qyunslation.structure.ingest import InputPreparationError, detect_input
from qyunslation.structure.models import CanvasKind, CoordinateUnit, LayoutMode, SourceFormat


def _content(path: Path, name: str) -> bytes:
    return (path / name).read_bytes()


def test_extracts_pdf_page_canvas(generated_structure_fixtures: Path):
    content = _content(generated_structure_fixtures, "single-column.pdf")

    canvases = extract_canvases(SourceFormat.PDF, content)

    assert len(canvases) == 1
    canvas = canvases[0]
    assert canvas.canvas_id == "page:1"
    assert canvas.kind is CanvasKind.PAGE
    assert canvas.unit is CoordinateUnit.PT
    assert canvas.width == pytest.approx(612)
    assert canvas.height == pytest.approx(792)
    assert canvas.layout_mode is LayoutMode.MIXED


def test_extracts_docx_section_and_column_count(generated_structure_fixtures: Path):
    content = _content(generated_structure_fixtures, "review.docx")

    canvases = extract_canvases(SourceFormat.DOCX, content)

    assert len(canvases) == 1
    canvas = canvases[0]
    assert canvas.canvas_id == "section:1"
    assert canvas.kind is CanvasKind.SECTION
    assert canvas.width == pytest.approx(612)
    assert canvas.height == pytest.approx(792)
    assert canvas.layout_mode is LayoutMode.DOUBLE
    assert canvas.source_geometry.details["column_count"] == 2


def test_applies_exif_orientation_to_image_canvas(generated_structure_fixtures: Path):
    content = _content(generated_structure_fixtures, "photo.jpg")

    canvases = extract_canvases(SourceFormat.JPEG, content)

    assert len(canvases) == 1
    canvas = canvases[0]
    assert (canvas.width, canvas.height) == (180, 320)
    assert canvas.rotation == 90
    assert canvas.source_geometry.details["exif_orientation"] == 6


def test_extracts_every_tiff_frame(generated_structure_fixtures: Path):
    content = _content(generated_structure_fixtures, "multipage.tiff")

    canvases = extract_canvases(SourceFormat.TIFF, content)

    assert [canvas.canvas_id for canvas in canvases] == ["page:1", "page:2"]
    assert all(canvas.unit is CoordinateUnit.PX for canvas in canvases)
    assert all((canvas.width, canvas.height) == (320, 180) for canvas in canvases)


def test_extracts_pptx_slide_canvas(generated_structure_fixtures: Path):
    content = _content(generated_structure_fixtures, "presentation.pptx")

    canvases = extract_canvases(SourceFormat.PPTX, content)

    assert len(canvases) == 1
    canvas = canvases[0]
    assert canvas.canvas_id == "slide:1"
    assert canvas.kind is CanvasKind.SLIDE
    assert canvas.unit is CoordinateUnit.PT
    assert canvas.width == pytest.approx(720)
    assert canvas.height == pytest.approx(540)
    assert canvas.layout_mode is LayoutMode.FREEFORM


def test_rejects_password_protected_pdf():
    source = pymupdf.open()
    source.new_page(width=300, height=400)
    content = source.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="user-secret",
    )
    source.close()
    assert detect_input("protected.pdf", content).source_format is SourceFormat.PDF

    with pytest.raises(InputPreparationError) as exc_info:
        extract_canvases(SourceFormat.PDF, content)

    assert exc_info.value.code == "DOCUMENT_ENCRYPTED"


def test_rejects_image_over_pixel_budget(generated_structure_fixtures: Path):
    content = _content(generated_structure_fixtures, "poster.png")

    with pytest.raises(InputPreparationError) as exc_info:
        extract_canvases(
            SourceFormat.PNG,
            content,
            limits=CanvasLimits(max_image_pixels=100, max_image_frames=10),
        )

    assert exc_info.value.code == "IMAGE_PIXEL_LIMIT_EXCEEDED"


def test_rejects_tiff_over_frame_budget(generated_structure_fixtures: Path):
    content = _content(generated_structure_fixtures, "multipage.tiff")

    with pytest.raises(InputPreparationError) as exc_info:
        extract_canvases(
            SourceFormat.TIFF,
            content,
            limits=CanvasLimits(max_image_pixels=1_000_000, max_image_frames=1),
        )

    assert exc_info.value.code == "IMAGE_FRAME_LIMIT_EXCEEDED"


def test_rejects_corrupt_ooxml_and_image_payloads():
    for source_format, content, expected_code in (
        (SourceFormat.DOCX, b"PK\x03\x04broken", "INVALID_CONTAINER"),
        (SourceFormat.PPTX, b"PK\x03\x04broken", "INVALID_CONTAINER"),
        (SourceFormat.PNG, b"\x89PNG\r\n\x1a\nbroken", "CANVAS_EXTRACTION_FAILED"),
    ):
        with pytest.raises(InputPreparationError) as exc_info:
            extract_canvases(source_format, content)
        assert exc_info.value.code == expected_code

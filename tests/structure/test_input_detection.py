from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from qyunslation.structure.ingest import (
    InputPreparationError,
    detect_input,
    sanitize_upload_name,
)
from qyunslation.structure.models import SourceFormat


@pytest.mark.parametrize(
    ("fixture_name", "expected_format", "expected_mime"),
    [
        ("single-column.pdf", SourceFormat.PDF, "application/pdf"),
        ("review.docx", SourceFormat.DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("poster.png", SourceFormat.PNG, "image/png"),
        ("photo.jpg", SourceFormat.JPEG, "image/jpeg"),
        ("diagram.webp", SourceFormat.WEBP, "image/webp"),
        ("scan.bmp", SourceFormat.BMP, "image/bmp"),
        ("multipage.tiff", SourceFormat.TIFF, "image/tiff"),
        ("presentation.pptx", SourceFormat.PPTX, "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ],
)
def test_detects_core_formats_from_content(
    generated_structure_fixtures: Path,
    fixture_name: str,
    expected_format: SourceFormat,
    expected_mime: str,
):
    content = (generated_structure_fixtures / fixture_name).read_bytes()

    detected = detect_input(fixture_name, content)

    assert detected.source_format is expected_format
    assert detected.detected_mime == expected_mime
    assert detected.source_sha256 == hashlib.sha256(content).hexdigest()
    assert detected.magic_family != "unknown"


def test_content_detection_accepts_extensionless_pdf():
    content = b"%PDF-1.7\n% fixture"

    detected = detect_input("upload", content)

    assert detected.source_format is SourceFormat.PDF
    assert detected.normalized_name == "upload.pdf"


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("legacy.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1payload", SourceFormat.DOC),
        ("legacy.ppt", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1payload", SourceFormat.PPT),
        ("vector.svg", b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'/>", SourceFormat.SVG),
        ("photo.heic", b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1", SourceFormat.HEIC),
        ("photo.avif", b"\x00\x00\x00\x18ftypavif\x00\x00\x00\x00avifmif1", SourceFormat.AVIF),
    ],
)
def test_detects_normalized_and_conditional_formats(
    filename: str,
    content: bytes,
    expected: SourceFormat,
):
    assert detect_input(filename, content).source_format is expected


def test_rejects_extension_content_mismatch():
    with pytest.raises(InputPreparationError) as exc_info:
        detect_input("disguised.jpg", b"%PDF-1.7\n")

    assert exc_info.value.code == "FORMAT_MISMATCH"


def test_rejects_specific_declared_mime_mismatch():
    with pytest.raises(InputPreparationError) as exc_info:
        detect_input("paper.pdf", b"%PDF-1.7\n", declared_mime="image/png")

    assert exc_info.value.code == "MIME_MISMATCH"


def test_allows_generic_declared_mime():
    detected = detect_input(
        "paper.pdf",
        b"%PDF-1.7\n",
        declared_mime="application/octet-stream",
    )

    assert detected.source_format is SourceFormat.PDF


@pytest.mark.parametrize(
    ("filename", "content", "code"),
    [
        ("empty.pdf", b"", "EMPTY_FILE"),
        ("payload.unknown", b"not a supported binary", "UNSUPPORTED_FORMAT"),
        ("broken.docx", b"PK\x03\x04not-a-package", "INVALID_CONTAINER"),
    ],
)
def test_rejects_empty_unknown_and_invalid_inputs(
    filename: str,
    content: bytes,
    code: str,
):
    with pytest.raises(InputPreparationError) as exc_info:
        detect_input(filename, content)

    assert exc_info.value.code == code


def test_rejects_suspicious_high_ratio_ooxml_container():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"x")
        archive.writestr("word/document.xml", b"0" * (2 * 1024 * 1024))

    with pytest.raises(InputPreparationError) as exc_info:
        detect_input("bomb.docx", output.getvalue())

    assert exc_info.value.code == "ARCHIVE_LIMIT_EXCEEDED"


def test_sanitizes_upload_names_without_preserving_paths_or_controls():
    assert sanitize_upload_name("../../report.pdf") == "report.pdf"
    assert sanitize_upload_name("C:\\private\\deck.pptx") == "deck.pptx"
    assert sanitize_upload_name("bad\x00name\n.pdf") == "badname.pdf"
    assert sanitize_upload_name("") == "uploaded_file"

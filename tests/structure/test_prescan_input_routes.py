from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.doc_image_prescan import file_sha256, scan_file_tier1


def test_prescan_hashes_the_complete_file(tmp_path: Path):
    payload = b"a" * (32 * 1024 * 1024) + b"different-tail"
    source = tmp_path / "large.bin"
    source.write_bytes(payload)

    assert file_sha256(source) == hashlib.sha256(payload).hexdigest()


def test_prescan_detects_tiff_frames_from_content(
    generated_structure_fixtures: Path,
    tmp_path: Path,
):
    source = generated_structure_fixtures / "multipage.tiff"
    renamed = tmp_path / "renamed-upload.bin"
    renamed.write_bytes(source.read_bytes())

    result = scan_file_tier1(renamed)

    assert result.file_type == "image"
    assert result.frame_count == 2
    assert result.error is None


def test_prescan_extracts_pptx_media_candidates(
    generated_structure_fixtures: Path,
):
    result = scan_file_tier1(generated_structure_fixtures / "presentation.pptx")

    assert result.file_type == "pptx"
    assert result.candidate_count == 1
    assert result.candidates[0].part_name
    assert result.candidates[0].part_name.startswith("ppt/media/")
    assert result.candidates[0].occurrence_index == 1
    assert result.error is None


def test_prescan_reports_format_mismatch_instead_of_zero_candidates(
    generated_structure_fixtures: Path,
    tmp_path: Path,
):
    source = generated_structure_fixtures / "photo.jpg"
    misleading = tmp_path / "photo.png"
    misleading.write_bytes(source.read_bytes())

    result = scan_file_tier1(misleading)

    assert result.file_type == "unsupported"
    assert result.error == "FORMAT_MISMATCH"
    assert "内容实际为 JPEG" in result.summary_text


def test_legacy_office_prescan_requires_normalization(tmp_path: Path):
    source = tmp_path / "legacy.ppt"
    source.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy")

    result = scan_file_tier1(source)

    assert result.file_type == "normalize_pptx"
    assert result.error == "normalization_required"

# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import stat
from pathlib import Path

import pytest
from fastapi import HTTPException

from qyunslation.api.v1 import _preview_target
from qyunslation.pipeline.office_preview import OfficePreviewError, office_to_pdf


@pytest.fixture(autouse=True)
def _roots(monkeypatch, tmp_path):
    monkeypatch.setenv("QYUNSLATION_PIPELINE_ROOT", str(tmp_path / "pipeline"))


def _docx(tmp_path: Path) -> Path:
    path = tmp_path / "doc.docx"
    path.write_bytes(b"PK\x03\x04 fake docx")
    return path


def _fake_soffice(tmp_path: Path, *, ok: bool) -> Path:
    script = tmp_path / "soffice"
    body = (
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('--outdir') + 1])\n"
    )
    body += "(out / 'in.pdf').write_bytes(b'%PDF-1.7 converted')\n" if ok else "sys.exit(3)\n"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_missing_soffice_has_stable_code(monkeypatch, tmp_path):
    monkeypatch.setenv("QYUNSLATION_SOFFICE", str(tmp_path / "nope"))
    with pytest.raises(OfficePreviewError) as err:
        office_to_pdf(_docx(tmp_path))
    assert err.value.code == "OFFICE_PREVIEW_UNAVAILABLE"
    with pytest.raises(HTTPException) as http:
        _preview_target(_docx(tmp_path), "application/octet-stream", "doc.docx")
    assert http.value.status_code == 501
    assert http.value.detail["code"] == "OFFICE_PREVIEW_UNAVAILABLE"


def test_conversion_success_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("QYUNSLATION_SOFFICE", str(_fake_soffice(tmp_path, ok=True)))
    docx = _docx(tmp_path)
    first = office_to_pdf(docx)
    assert first.read_bytes().startswith(b"%PDF")
    monkeypatch.setenv("QYUNSLATION_SOFFICE", str(tmp_path / "gone"))
    assert office_to_pdf(docx) == first
    path, media, filename = _preview_target(docx, "x", "report.docx")
    assert media == "application/pdf" and filename == "report.preview.pdf" and path == first


def test_conversion_failure_has_stable_code(monkeypatch, tmp_path):
    monkeypatch.setenv("QYUNSLATION_SOFFICE", str(_fake_soffice(tmp_path, ok=False)))
    with pytest.raises(HTTPException) as http:
        _preview_target(_docx(tmp_path), "x", "doc.docx")
    assert http.value.status_code == 502
    assert http.value.detail["code"] == "OFFICE_PREVIEW_FAILED"


def test_images_stream_directly(tmp_path):
    image = tmp_path / "scan.PNG"
    image.write_bytes(b"\x89PNG")
    path, media, _ = _preview_target(image, "application/octet-stream", "scan.png")
    assert path == image and media == "image/png"

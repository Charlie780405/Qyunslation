from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from qyunslation.converter.office import LibreOfficeConverter, OfficeConversion
from qyunslation.structure.ingest import InputPreparationError
from qyunslation.structure.models import SourceFormat


class FakeRunner:
    def __init__(self, output: bytes | None, *, returncode: int = 0, stderr: str = ""):
        self.output = output
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command: list[str], **kwargs):
        self.calls.append((command, kwargs))
        if self.output is not None:
            output_dir = Path(command[command.index("--outdir") + 1])
            source = Path(command[-1])
            target = "docx" if source.suffix == ".doc" else "pptx"
            (output_dir / f"input.{target}").write_bytes(self.output)
        return subprocess.CompletedProcess(
            command,
            self.returncode,
            stdout="conversion output",
            stderr=self.stderr,
        )


@pytest.mark.parametrize(
    ("source_name", "source_format", "fixture_name", "target_format", "target_suffix"),
    [
        ("legacy.doc", SourceFormat.DOC, "review.docx", SourceFormat.DOCX, ".docx"),
        ("legacy.ppt", SourceFormat.PPT, "presentation.pptx", SourceFormat.PPTX, ".pptx"),
    ],
)
def test_normalizes_legacy_office_without_shell_or_user_paths(
    generated_structure_fixtures: Path,
    source_name: str,
    source_format: SourceFormat,
    fixture_name: str,
    target_format: SourceFormat,
    target_suffix: str,
):
    output = (generated_structure_fixtures / fixture_name).read_bytes()
    runner = FakeRunner(output)
    converter = LibreOfficeConverter(
        executable="/usr/bin/soffice",
        version="LibreOffice test",
        runner=runner,
    )

    result = converter.convert(
        "../../private/" + source_name,
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy",
        source_format,
    )

    assert isinstance(result, OfficeConversion)
    assert result.output_format is target_format
    assert result.output_name == f"legacy{target_suffix}"
    assert result.content == output
    assert result.converter == "libreoffice"
    assert result.converter_version == "LibreOffice test"

    command, kwargs = runner.calls[0]
    assert isinstance(command, list)
    assert command[0] == "/usr/bin/soffice"
    assert "--headless" in command
    assert command[-1].endswith(f"input{Path(source_name).suffix}")
    assert "private" not in " ".join(command)
    assert any(arg.startswith("-env:UserInstallation=file:") for arg in command)
    assert "shell" not in kwargs
    assert kwargs["timeout"] == 120


def test_missing_libreoffice_fails_before_writing_input():
    converter = LibreOfficeConverter(executable=None, command_finder=lambda _: None)

    with pytest.raises(InputPreparationError) as exc_info:
        converter.convert("legacy.ppt", b"ole", SourceFormat.PPT)

    assert exc_info.value.code == "OFFICE_CONVERTER_UNAVAILABLE"


def test_conversion_timeout_has_stable_error_code():
    def timeout_runner(command: list[str], **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    converter = LibreOfficeConverter(
        executable="/usr/bin/soffice",
        runner=timeout_runner,
    )

    with pytest.raises(InputPreparationError) as exc_info:
        converter.convert("legacy.doc", b"ole", SourceFormat.DOC)

    assert exc_info.value.code == "OFFICE_CONVERSION_TIMEOUT"


def test_nonzero_exit_is_sanitized_and_rejected():
    runner = FakeRunner(None, returncode=7, stderr="bad\n\x00detail" + "x" * 5_000)
    converter = LibreOfficeConverter(executable="/usr/bin/soffice", runner=runner)

    with pytest.raises(InputPreparationError) as exc_info:
        converter.convert("legacy.ppt", b"ole", SourceFormat.PPT)

    assert exc_info.value.code == "OFFICE_CONVERSION_FAILED"
    assert "\x00" not in exc_info.value.message
    assert len(exc_info.value.message) < 1_500


def test_missing_output_is_rejected():
    converter = LibreOfficeConverter(
        executable="/usr/bin/soffice",
        runner=FakeRunner(None),
    )

    with pytest.raises(InputPreparationError) as exc_info:
        converter.convert("legacy.doc", b"ole", SourceFormat.DOC)

    assert exc_info.value.code == "OFFICE_OUTPUT_MISSING"


def test_wrong_output_format_is_rejected():
    converter = LibreOfficeConverter(
        executable="/usr/bin/soffice",
        runner=FakeRunner(b"%PDF-1.7\n"),
    )

    with pytest.raises(InputPreparationError) as exc_info:
        converter.convert("legacy.doc", b"ole", SourceFormat.DOC)

    assert exc_info.value.code == "OFFICE_OUTPUT_INVALID"


def test_non_legacy_format_is_rejected():
    converter = LibreOfficeConverter(executable="/usr/bin/soffice")

    with pytest.raises(InputPreparationError) as exc_info:
        converter.convert("paper.pdf", b"%PDF", SourceFormat.PDF)

    assert exc_info.value.code == "OFFICE_SOURCE_FORMAT_UNSUPPORTED"


@pytest.mark.skipif(
    __import__("shutil").which("soffice") is None
    and __import__("shutil").which("libreoffice") is None,
    reason="LibreOffice not installed; run scripts/install-libreoffice.sh",
)
def test_real_libreoffice_converts_doc_fixture_to_docx(generated_structure_fixtures: Path):
    """End-to-end conversion without FakeRunner (PLAN-030e Task 1)."""
    expected = (generated_structure_fixtures / "review.docx").read_bytes()
    ole_header = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    converter = LibreOfficeConverter()

    result = converter.convert("legacy.doc", ole_header + b"legacy", SourceFormat.DOC)

    assert result.output_format is SourceFormat.DOCX
    assert result.content.startswith(b"PK")
    assert len(result.content) > 100
    import io
    import zipfile

    names = zipfile.ZipFile(io.BytesIO(result.content)).namelist()
    assert "word/document.xml" in names

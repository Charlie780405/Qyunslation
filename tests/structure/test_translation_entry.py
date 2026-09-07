from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from qyunslation.core.schemas import TranslatePayload
from qyunslation.server.core import (
    TranslationService,
    get_workflow_type_from_filename,
    prepare_translation_input,
)
from qyunslation.server.uploads import read_upload_limited
from qyunslation.structure.capabilities import RuntimeFeature
from qyunslation.structure.ingest import InputPreparationError
from qyunslation.structure.runtime import FeatureProbe, RuntimeCapabilitySnapshot


class ChunkedUpload:
    def __init__(self, chunks: list[bytes]):
        self.chunks = iter(chunks)

    async def read(self, size: int = -1) -> bytes:
        return next(self.chunks, b"")


def _available_runtime() -> RuntimeCapabilitySnapshot:
    return RuntimeCapabilitySnapshot(
        probes=[
            FeatureProbe(feature=feature, available=True, detail="test")
            for feature in RuntimeFeature
        ]
    )


async def test_upload_reader_enforces_limit_while_streaming():
    upload = ChunkedUpload([b"abcd", b"efgh", b""])

    with pytest.raises(InputPreparationError) as exc_info:
        await read_upload_limited(upload, max_bytes=7, chunk_size=4)

    assert exc_info.value.code == "UPLOAD_TOO_LARGE"
    assert exc_info.value.http_status == 413


async def test_upload_reader_accepts_exact_limit():
    upload = ChunkedUpload([b"abcd", b"efg", b""])

    assert await read_upload_limited(upload, max_bytes=7, chunk_size=4) == b"abcdefg"


def test_extension_router_is_explicit_and_never_defaults_to_text():
    assert get_workflow_type_from_filename("poster.tiff") == "image_overlay"
    assert get_workflow_type_from_filename("old.ppt") == "normalize_pptx"
    assert get_workflow_type_from_filename("old.doc") == "normalize_docx"
    assert get_workflow_type_from_filename("opaque.unknown") == "unsupported"


def test_translation_input_uses_normalized_content_route_and_safe_audit(
    generated_structure_fixtures: Path,
):
    source = generated_structure_fixtures / "presentation.pptx"

    prepared = prepare_translation_input(
        source.name,
        source.read_bytes(),
        declared_mime=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
        runtime_snapshot=_available_runtime(),
    )

    assert prepared.workflow_type == "pptx"
    assert prepared.is_structured_input is True
    assert prepared.ingest_audit is not None
    assert prepared.ingest_audit["canvas_count"] == 1
    assert "content" not in prepared.ingest_audit
    assert "PK" not in repr(prepared)


def test_translation_input_rejects_unknown_binary():
    with pytest.raises(InputPreparationError) as exc_info:
        prepare_translation_input("opaque.unknown", b"not-a-supported-file")

    assert exc_info.value.code == "UNSUPPORTED_FORMAT"
    assert exc_info.value.http_status == 415


def test_translation_input_preserves_existing_text_workflow():
    prepared = prepare_translation_input("notes.txt", "hello".encode())

    assert prepared.workflow_type == "txt"
    assert prepared.file_contents == b"hello"
    assert prepared.ingest_audit is None
    assert prepared.is_structured_input is False


async def test_service_records_ingest_audit_before_scheduling(
    generated_structure_fixtures: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    service = TranslationService()
    source = generated_structure_fixtures / "single-column.pdf"
    payload = TypeAdapter(TranslatePayload).validate_python(
        {"workflow_type": "auto", "skip_translate": True}
    )

    async def no_op_translation(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_perform_translation", no_op_translation)
    await service.start_translation(
        "task-030b",
        payload,
        source.read_bytes(),
        source.name,
        declared_mime="application/pdf",
    )
    await service.tasks_state["task-030b"]["current_task_ref"]

    state = service.tasks_state["task-030b"]
    assert state["ingest"]["source_format"] == "PDF"
    assert state["ingest"]["canvas_count"] == 1
    assert "content" not in state["ingest"]


def test_file_upload_endpoint_returns_413_before_task_creation(
    monkeypatch: pytest.MonkeyPatch,
):
    from qyunslation.app import app

    monkeypatch.setenv("QYUNSLATION_MAX_UPLOAD_BYTES", "3")
    response = TestClient(app).post(
        "/service/translate/file",
        files={"file": ("paper.pdf", b"1234", "application/pdf")},
        data={"payload": json.dumps({"workflow_type": "auto", "skip_translate": True})},
    )

    assert response.status_code == 413
    assert "超过 3 字节" in response.json()["detail"]


def test_file_upload_endpoint_rejects_declared_mime_mismatch(
    generated_structure_fixtures: Path,
):
    from qyunslation.app import app

    content = (generated_structure_fixtures / "single-column.pdf").read_bytes()
    response = TestClient(app).post(
        "/service/translate/file",
        files={"file": ("paper.pdf", content, "image/png")},
        data={"payload": json.dumps({"workflow_type": "auto", "skip_translate": True})},
    )

    assert response.status_code == 415
    assert "MIME" in response.json()["detail"]

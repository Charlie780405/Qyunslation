"""PLAN-033g：Manifest 1.2.0 执行契约与模型溯源。"""
from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from qyunslation.structure import (
    CURRENT_SCHEMA_VERSION,
    DocumentStructureManifest,
    build_manifest_id,
)
from qyunslation.structure.model_trace import (
    _CURRENT_TRACE,
    apply_current_model_trace,
    build_model_trace,
    resolve_model_trace,
)
from qyunslation.structure.models import (
    BlockRole,
    SourceStyle,
    TranslationPolicy,
    TranslatableBlock,
)
from qyunslation.structure.scan_pdf import PDF_STRUCTURE_SCANNER_VERSION
from tests.structure.test_manifest_contract import SOURCE_SHA256, _minimal_manifest


def test_schema_and_scanner_versions_for_033g():
    assert CURRENT_SCHEMA_VERSION == "1.2.0"
    assert PDF_STRUCTURE_SCANNER_VERSION == "1.7.0"


def test_v1_1_manifest_still_validates_without_new_block_fields():
    payload = _minimal_manifest()
    payload["schema_version"] = "1.1.0"
    payload["manifest_id"] = build_manifest_id(SOURCE_SHA256, "1.1.0")
    manifest = DocumentStructureManifest.model_validate(payload)
    assert manifest.objects[0].translatable_blocks == []


def test_translatable_block_carries_role_policy_style_and_table_span():
    block = TranslatableBlock(
        block_id="t1:r0c1",
        source_text="Endpoint",
        role=BlockRole.TABLE_HEADER,
        translation_policy=TranslationPolicy.TRANSLATE,
        source_style=SourceStyle(
            font_name="Times-Bold",
            font_size=9.0,
            font_weight="bold",
            italic=False,
            alignment="center",
            rotation=90.0,
            writing_direction="ltr",
        ),
        row_index=0,
        column_index=1,
        row_span=1,
        column_span=2,
    )
    assert block.role is BlockRole.TABLE_HEADER
    assert block.source_style.font_weight == "bold"
    assert block.column_span == 2


def test_terminal_success_rejects_pending_objects():
    payload = _minimal_manifest()
    payload["extensions"] = {"terminal": True}

    with pytest.raises(ValidationError) as exc_info:
        DocumentStructureManifest.model_validate(payload)

    assert "MANIFEST_PENDING_IN_SUCCESS" in str(exc_info.value)


def test_scan_manifest_may_still_contain_pending():
    manifest = DocumentStructureManifest.model_validate(_minimal_manifest())
    assert manifest.objects[0].execution_status.value == "PENDING"


def test_output_evidence_records_block_level_execution():
    payload = _minimal_manifest()
    payload["objects"][0]["execution_status"] = "TRANSLATED"
    payload["objects"][0]["output_evidence"] = {
        "checks": {},
        "blocks": [
            {
                "block_id": "fig:1:title",
                "detection": "caption_anchor",
                "queued": True,
                "translated": True,
                "laid_out": True,
                "validated": True,
                "qc": ["FONT_BELOW_TARGET"],
                "final_font_size": 6.5,
                "final_font_weight": "bold",
                "output_bbox": {"x0": 40, "y0": 120, "x1": 200, "y1": 140},
            }
        ],
    }
    manifest = DocumentStructureManifest.model_validate(payload)
    evidence = manifest.objects[0].output_evidence
    assert evidence is not None
    assert evidence.blocks[0].qc == ["FONT_BELOW_TARGET"]
    assert evidence.blocks[0].final_font_weight == "bold"


def test_model_trace_strips_credentials_and_rejects_api_key():
    trace = build_model_trace(
        model_id="qwen3.6:35b-a3b",
        endpoint="http://user:secret@100.67.66.123:11434/v1?api_key=sk-test",
    )
    assert trace == {
        "model_id": "qwen3.6:35b-a3b",
        "endpoint": "http://100.67.66.123:11434/v1",
    }
    dumped = str(trace)
    assert "secret" not in dumped
    assert "sk-test" not in dumped
    assert "api_key" not in dumped

    with pytest.raises(ValueError, match="MODEL_TRACE_SECRET"):
        build_model_trace(
            model_id="qwen3.6:35b-a3b",
            endpoint="http://100.67.66.123:11434/v1",
            extras={"api_key": "sk-leak"},
        )


def test_model_trace_uses_resolved_task_values_not_defaults():
    trace = resolve_model_trace(
        model_id="user-override-model",
        endpoint="http://100.67.66.123:11434/v1",
        default_model_id="qwen3.6:35b-a3b",
        default_endpoint="http://example.invalid/v1",
    )
    assert trace["model_id"] == "user-override-model"
    assert trace["endpoint"] == "http://100.67.66.123:11434/v1"


def test_terminal_manifest_rejects_model_trace_secrets():
    payload = deepcopy(_minimal_manifest())
    payload["objects"][0]["execution_status"] = "TRANSLATED"
    payload["extensions"] = {
        "terminal": True,
        "model_trace": {
            "model_id": "qwen3.6:35b-a3b",
            "endpoint": "http://100.67.66.123:11434/v1",
            "api_key": "sk-leak",
        },
    }
    with pytest.raises(ValidationError) as exc_info:
        DocumentStructureManifest.model_validate(payload)
    assert "MODEL_TRACE_SECRET" in str(exc_info.value)


def test_apply_current_model_trace_falls_back_to_env(monkeypatch):
    class Holder:
        def __init__(self) -> None:
            self.extensions: dict = {}

    holder = Holder()
    monkeypatch.setenv("DOCUTRANSLATE_MODEL_ID", "qwen3.6:35b-a3b")
    monkeypatch.setenv("DOCUTRANSLATE_BASE_URL", "http://100.67.66.123:11434/v1")
    token = _CURRENT_TRACE.set(None)
    try:
        apply_current_model_trace(holder)
    finally:
        _CURRENT_TRACE.reset(token)
    assert holder.extensions["model_trace"]["model_id"] == "qwen3.6:35b-a3b"
    assert holder.extensions["model_trace"]["endpoint"] == "http://100.67.66.123:11434/v1"

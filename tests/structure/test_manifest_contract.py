import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from qyunslation.structure import (
    CURRENT_SCHEMA_VERSION,
    DocumentStructureManifest,
    FigureObject,
    build_manifest_id,
    build_object_id,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs/contracts/document-structure-manifest-v1.schema.json"
SOURCE_SHA256 = "a" * 64
OBJECT_ID = "obj:" + "b" * 64


def _minimal_manifest() -> dict:
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "manifest_id": build_manifest_id(SOURCE_SHA256, CURRENT_SCHEMA_VERSION),
        "created_at": "2026-09-07T12:00:00Z",
        "producer": {"name": "qyunslation", "version": "test"},
        "document": {
            "source_sha256": SOURCE_SHA256,
            "source_name": "paper.pdf",
            "source_format": "PDF",
            "detected_mime": "application/pdf",
            "content_profile": "RESEARCH_ARTICLE",
            "profile_source": "AUTO",
            "profile_confidence": 0.98,
            "profile_evidence": ["numbered figure captions"],
            "requested_mode": "NATIVE",
            "selected_mode": "NATIVE",
            "output_editability": "EDITABLE",
            "input_asset": {
                "asset_id": "source",
                "role": "INPUT",
                "sha256": SOURCE_SHA256,
                "media_type": "application/pdf",
                "locator": "external:paper.pdf",
            },
        },
        "canvases": [
            {
                "canvas_id": "page:1",
                "kind": "PAGE",
                "source_index": 1,
                "width": 612,
                "height": 792,
                "unit": "PT",
                "rotation": 0,
                "layout_mode": "DOUBLE",
            }
        ],
        "objects": [
            {
                "type": "FIGURE",
                "object_id": OBJECT_ID,
                "canvas_id": "page:1",
                "bbox": {"x0": 36, "y0": 120, "x1": 576, "y1": 360},
                "representation": "HYBRID",
                "source_refs": [
                    {
                        "kind": "PDF_XREF",
                        "ref": "xref:17",
                        "occurrence_index": 1,
                    }
                ],
                "execution_status": "PENDING",
                "semantic_id": "figure:1",
                "semantic_scope": "main",
                "caption_ids": [],
                "child_object_ids": [],
            }
        ],
        "issues": [],
    }


def test_manifest_round_trip_uses_discriminated_objects_and_derived_summary():
    manifest = DocumentStructureManifest.model_validate(_minimal_manifest())

    assert isinstance(manifest.objects[0], FigureObject)
    assert manifest.summary.figure_count == 1
    assert manifest.summary.table_count == 0
    assert manifest.summary.object_counts == {"FIGURE": 1}
    assert DocumentStructureManifest.model_validate_json(
        manifest.model_dump_json()
    ) == manifest


def test_same_major_unknown_optional_fields_survive_round_trip():
    payload = _minimal_manifest()
    payload["schema_version"] = "1.7.0"
    payload["future_top_level"] = {"enabled": True}
    payload["document"]["future_document_field"] = "kept"

    manifest = DocumentStructureManifest.model_validate(payload)
    dumped = manifest.model_dump(mode="json")

    assert dumped["future_top_level"] == {"enabled": True}
    assert dumped["document"]["future_document_field"] == "kept"


@pytest.mark.parametrize("version", ["2.0.0", "0.9.0", "v1", "1.0"])
def test_unsupported_or_malformed_schema_versions_fail_closed(version: str):
    payload = _minimal_manifest()
    payload["schema_version"] = version

    with pytest.raises(ValidationError) as exc_info:
        DocumentStructureManifest.model_validate(payload)

    assert "MANIFEST_VERSION_UNSUPPORTED" in str(exc_info.value)


def test_source_identity_requires_full_lowercase_sha256():
    payload = _minimal_manifest()
    payload["document"]["source_sha256"] = "a" * 63

    with pytest.raises(ValidationError):
        DocumentStructureManifest.model_validate(payload)


@pytest.mark.parametrize(
    "bbox",
    [
        {"x0": -1, "y0": 0, "x1": 10, "y1": 10},
        {"x0": 10, "y0": 0, "x1": 10, "y1": 10},
        {"x0": 0, "y0": 0, "x1": 613, "y1": 10},
        {"x0": 0, "y0": 700, "x1": 10, "y1": 793},
    ],
)
def test_object_bbox_must_be_positive_and_inside_its_canvas(bbox: dict):
    payload = _minimal_manifest()
    payload["objects"][0]["bbox"] = bbox

    with pytest.raises(ValidationError) as exc_info:
        DocumentStructureManifest.model_validate(payload)

    assert "MANIFEST_BBOX_INVALID" in str(exc_info.value)


def test_duplicate_object_ids_and_semantic_ids_fail_closed():
    duplicate_id = _minimal_manifest()
    duplicate_id["objects"].append(deepcopy(duplicate_id["objects"][0]))
    duplicate_id["objects"][1]["semantic_id"] = "figure:2"

    with pytest.raises(ValidationError) as id_error:
        DocumentStructureManifest.model_validate(duplicate_id)
    assert "MANIFEST_OBJECT_ID_DUPLICATE" in str(id_error.value)

    duplicate_semantic = _minimal_manifest()
    duplicate_semantic["objects"].append(deepcopy(duplicate_semantic["objects"][0]))
    duplicate_semantic["objects"][1]["object_id"] = "obj:" + "c" * 64

    with pytest.raises(ValidationError) as semantic_error:
        DocumentStructureManifest.model_validate(duplicate_semantic)
    assert "MANIFEST_SEMANTIC_ID_DUPLICATE" in str(semantic_error.value)


def test_contradictory_caller_summary_is_rejected():
    payload = _minimal_manifest()
    payload["summary"] = {"figure_count": 7, "table_count": 0}

    with pytest.raises(ValidationError) as exc_info:
        DocumentStructureManifest.model_validate(payload)

    assert "MANIFEST_SUMMARY_MISMATCH" in str(exc_info.value)


@pytest.mark.parametrize(
    "status", ["EXPLICITLY_SKIPPED", "FAILED_SOFT", "FAILED_HARD"]
)
def test_skip_and_failure_states_require_a_reason_code(status: str):
    payload = _minimal_manifest()
    payload["objects"][0]["execution_status"] = status

    with pytest.raises(ValidationError) as exc_info:
        DocumentStructureManifest.model_validate(payload)

    assert "MANIFEST_REASON_REQUIRED" in str(exc_info.value)


def test_issue_object_reference_must_exist():
    payload = _minimal_manifest()
    payload["issues"] = [
        {
            "code": "OCR_LOW_CONFIDENCE",
            "severity": "WARNING",
            "stage": "SCAN",
            "object_id": "obj:" + "f" * 64,
            "retryable": True,
            "message": "OCR confidence is low",
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        DocumentStructureManifest.model_validate(payload)

    assert "MANIFEST_ISSUE_OBJECT_UNKNOWN" in str(exc_info.value)


def test_auto_and_user_override_profile_evidence_is_explicit():
    auto_payload = _minimal_manifest()
    auto_payload["document"]["profile_evidence"] = []
    with pytest.raises(ValidationError):
        DocumentStructureManifest.model_validate(auto_payload)

    override_payload = _minimal_manifest()
    override_payload["document"].update(
        {
            "content_profile": "POSTER",
            "profile_source": "USER_OVERRIDE",
            "profile_confidence": None,
            "profile_evidence": [],
            "auto_profile_suggestion": "RESEARCH_ARTICLE",
        }
    )
    assert (
        DocumentStructureManifest.model_validate(override_payload)
        .document.auto_profile_suggestion.value
        == "RESEARCH_ARTICLE"
    )


def test_manifest_and_object_ids_are_deterministic():
    refs_a = [{"kind": "PDF_XREF", "ref": "xref:17"}]
    refs_b = [{"ref": "xref:17", "kind": "PDF_XREF"}]

    assert build_manifest_id(SOURCE_SHA256, "1.0.0") == build_manifest_id(
        SOURCE_SHA256, "1.9.0"
    )
    assert build_object_id(
        SOURCE_SHA256, "page:1", "FIGURE", "main:figure:1", refs_a
    ) == build_object_id(
        SOURCE_SHA256, "page:1", "FIGURE", "main:figure:1", refs_b
    )


def test_committed_json_schema_matches_model():
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    generated = DocumentStructureManifest.model_json_schema()

    assert committed == generated

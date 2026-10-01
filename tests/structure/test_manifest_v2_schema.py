# SPDX-License-Identifier: MPL-2.0
"""PLAN-071b：Manifest 2.0 字段与 1.3 兼容读取。"""
from __future__ import annotations

from copy import deepcopy

from qyunslation.structure.models import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_MAJORS,
    DocumentStructureManifest,
    PreserveKind,
    build_manifest_id,
)
from qyunslation.pipeline.stages import build_minimal_manifest


SOURCE = "a" * 64


def test_current_schema_is_2():
    assert CURRENT_SCHEMA_VERSION.startswith("2.")
    assert 1 in SUPPORTED_SCHEMA_MAJORS
    assert 2 in SUPPORTED_SCHEMA_MAJORS


def test_minimal_manifest_has_preserve_and_reverse_index():
    manifest = build_minimal_manifest(
        source_sha256=SOURCE,
        source_name="x.pdf",
        source_format="pdf",
        page_or_slide_count=2,
    )
    assert manifest.schema_version == CURRENT_SCHEMA_VERSION
    assert manifest.manifest_id == build_manifest_id(SOURCE, CURRENT_SCHEMA_VERSION)
    assert manifest.reverse_index
    for obj in manifest.objects:
        assert obj.preserve_kind is PreserveKind.NONE
        key = f"{obj.canvas_id}:{obj.type.value.lower()}"
        assert manifest.reverse_index[key] == obj.object_id


def test_reverse_lookup_from_product_key():
    manifest = build_minimal_manifest(
        source_sha256=SOURCE,
        source_name="x.pdf",
        source_format="pdf",
        page_or_slide_count=1,
    )
    product_key = "page:1:body"
    object_id = manifest.reverse_index[product_key]
    found = next(item for item in manifest.objects if item.object_id == object_id)
    assert found.canvas_id == "page:1"


def test_read_legacy_1_3_0_payload():
    manifest = build_minimal_manifest(
        source_sha256=SOURCE,
        source_name="legacy.pdf",
        source_format="pdf",
    )
    data = manifest.model_dump(mode="json")
    # Simulate a 1.3.0 document still in the wild.
    data["schema_version"] = "1.3.0"
    data["manifest_id"] = build_manifest_id(SOURCE, "1.3.0")
    for obj in data["objects"]:
        obj.pop("preserve_kind", None)
        obj.pop("source_object_hash", None)
    data.pop("reverse_index", None)
    again = DocumentStructureManifest.model_validate(deepcopy(data))
    assert again.schema_version == "1.3.0"
    assert again.reverse_index == {}
    assert again.objects[0].preserve_kind is PreserveKind.NONE

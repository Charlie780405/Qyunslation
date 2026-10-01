# SPDX-License-Identifier: MPL-2.0
"""PLAN-071a：金标 expectation JSON 契约（无第三方 jsonschema 依赖）。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "docs" / "gold" / "plan071"
SCHEMA_PATH = GOLD / "expectation.schema.json"
CATALOG_PATH = GOLD / "catalog.json"
EXP_DIR = GOLD / "expectations"

REQUIRED_FORMATS = {
    "pdf_text",
    "pdf_scan",
    "pdf_table_dense",
    "pdf_figure_dense",
    "docx",
    "pptx",
    "image",
}

REQUIRED_TOP = {
    "id",
    "format",
    "page_or_slide_count",
    "objects",
    "atomic_spans",
    "quality_rules",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_expectation(data: dict, *, filename: str) -> None:
    missing = REQUIRED_TOP - set(data)
    assert not missing, f"{filename}: missing {missing}"
    assert data["format"] in REQUIRED_FORMATS, data["format"]
    assert isinstance(data["page_or_slide_count"], int) and data["page_or_slide_count"] >= 1
    objects = data["objects"]
    for key in ("paragraphs_min", "tables", "figures", "preserve"):
        assert key in objects, f"{filename}: objects.{key}"
    assert isinstance(data["atomic_spans"], list)
    assert isinstance(data["quality_rules"], list) and data["quality_rules"]
    for rule in data["quality_rules"]:
        assert rule["severity"] in {"blocker", "warning", "info"}
        assert rule.get("id") and rule.get("rule")
    for span in data["atomic_spans"]:
        assert span.get("kind")
        assert span.get("examples")


def test_schema_file_parses():
    schema = _load(SCHEMA_PATH)
    assert schema["title"] == "PLAN-071 gold expectation"
    assert "properties" in schema


def test_catalog_covers_seven_formats():
    catalog = _load(CATALOG_PATH)
    formats = {e["format"] for e in catalog["entries"]}
    assert formats == REQUIRED_FORMATS
    assert len(catalog["entries"]) == 7


def test_each_catalog_entry_has_expectation_file():
    catalog = _load(CATALOG_PATH)
    for entry in catalog["entries"]:
        path = GOLD / entry["expectation"]
        assert path.is_file(), entry["expectation"]
        data = _load(path)
        assert data["id"] == entry["id"]
        assert data["format"] == entry["format"]
        _validate_expectation(data, filename=path.name)


def test_fda_expectation_forbids_th_artifact():
    data = _load(EXP_DIR / "G071-pdf-scan-fda.json")
    assert data["page_or_slide_count"] == 20
    assert "^{th}" in data["layout_baseline"]["forbid_substrings"]
    severities = {r["id"]: r["severity"] for r in data["quality_rules"]}
    assert severities["fda-logo-preserve"] == "blocker"
    assert severities["qa-review-required"] == "blocker"


def test_baseline_manifest_exists():
    manifest = GOLD / "baseline" / "MANIFEST.md"
    assert manifest.is_file()
    text = manifest.read_text(encoding="utf-8")
    assert "dae7401230ca270f1cedfa2052235dba5952d4f0a577e91dc84c36c0ba7b9cb4" in text

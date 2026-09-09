"""PLAN-033l：执行 Manifest 总门与终态产物优先。"""
from __future__ import annotations

from qyunslation.structure import DocumentStructureManifest
from qyunslation.structure.plan033_final import attach_execution_assertions
from tests.structure.test_manifest_contract import SOURCE_SHA256, _minimal_manifest


def test_execution_gate_requires_model_and_hires_when_below_target():
    payload = _minimal_manifest()
    payload["objects"][0]["execution_status"] = "TRANSLATED"
    payload["objects"][0]["output_evidence"] = {
        "checks": {"object_qc": ["FONT_BELOW_TARGET"], "dpi": None},
        "blocks": [],
    }
    payload["extensions"] = {
        "terminal": True,
        "model_trace": {
            "model_id": "qwen3.6:35b-a3b",
            "endpoint": "http://100.67.66.123:11434/v1",
        }
    }
    exe = DocumentStructureManifest.model_validate(payload)
    report: dict = {"fail": [], "pass": [], "model_trace": None}
    attach_execution_assertions(report, SOURCE_SHA256, exe=exe)
    assert "model_trace" in report["pass"]
    assert "figure:figure:1" in report["pass"]
    assert any(item.startswith("FIGURE_DPI:figure:1") for item in report["fail"])


def test_execution_gate_missing_manifest_fails():
    report: dict = {"fail": [], "pass": [], "model_trace": None}
    attach_execution_assertions(report, SOURCE_SHA256, exe=None)
    assert report["fail"] == ["EXECUTION_MANIFEST_MISSING"]

# SPDX-License-Identifier: MPL-2.0
"""PLAN-050c/e：状态机 + Manifest 摘要 + QA 门禁。"""
from __future__ import annotations

import json

import pytest

from qyunslation.ui.manifest_view import ManifestViewError, summarize_for_ui
from qyunslation.ui.qa import export_gate, qa_items
from qyunslation.ui.state import normalize_task_state


def test_unknown_state_is_degraded_not_success():
    assert normalize_task_state("") == "degraded"
    assert normalize_task_state(None) == "degraded"
    assert normalize_task_state("translating page 3") == "translating"
    assert normalize_task_state("done") == "succeeded"


def test_truncated_counts_are_unknown_not_zero():
    payload = {
        "schema_version": "1.3.0",
        "summary": {"figure_count": 0, "table_count": 0, "object_counts": {}},
        "canvases": [{}],
        "issues": [
            {
                "code": "SCAN_TRUNCATED",
                "severity": "WARNING",
                "stage": "SCAN",
                "message": "truncated",
            }
        ],
        "objects": [],
    }
    card = summarize_for_ui(payload)
    assert card["status"] == "truncated"
    assert card["figure_count"] == "unknown"
    assert card["display"]["figures"] == "—"


def test_ljae439_semantic_counts():
    payload = {
        "schema_version": "1.3.0",
        "summary": {
            "figure_count": 5,
            "table_count": 3,
            "object_counts": {"IMAGE": 2},
        },
        "canvases": [{}] * 8,
        "issues": [],
        "objects": [],
    }
    card = summarize_for_ui(payload)
    assert card["figure_count"] == 5
    assert card["table_count"] == 3
    assert card["page_count"] == 8
    assert card["status"] == "ok"


def test_bad_major_fail_closed():
    for version in ("3.0.0", "0.9.0", "", "x.y.z"):
        with pytest.raises(ManifestViewError, match="VERSION"):
            summarize_for_ui({"schema_version": version, "summary": {}})


def test_manifest_2_is_supported():
    """PLAN-080h：Manifest 2.0 的摘要字段与 1.x 一致，不得再被当作不支持的版本。"""
    card = summarize_for_ui(
        {
            "schema_version": "2.0.0",
            "canvases": [{}, {}],
            "summary": {"figure_count": 4, "table_count": 2, "physical_image_count": 6},
        }
    )
    assert card["figure_count"] == 4
    assert card["table_count"] == 2
    assert card["physical_image_count"] == 6
    assert card["page_count"] == 2


def test_missing_summary_fail_closed():
    with pytest.raises(ManifestViewError, match="SUMMARY"):
        summarize_for_ui({"schema_version": "1.0.0", "objects": []})


def test_export_gate_blocks_on_error():
    items = qa_items(
        {
            "issues": [
                {
                    "code": "DOSE_MISMATCH",
                    "severity": "ERROR",
                    "stage": "VALIDATE",
                    "message": "dose",
                    "object_id": "obj:1",
                }
            ]
        }
    )
    gate = export_gate(items)
    assert gate["formal_export"] is False
    assert gate["review_export"] is True
    assert gate["blocking_count"] == 1


def test_summarize_accepts_json_string():
    raw = json.dumps(
        {
            "schema_version": "1.2.0",
            "summary": {"figure_count": 1, "table_count": 0},
            "canvases": [{}],
            "issues": [],
            "objects": [],
        }
    )
    assert summarize_for_ui(raw)["figure_count"] == 1

# SPDX-License-Identifier: MPL-2.0
"""PLAN-051b：MQM 计分夹具（不跑 Ollama）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qyunslation.gold.plan034 import evaluate_baseline_report, load_thresholds
from qyunslation.gold.plan051_score import (
    Plan051ScoreError,
    aggregate_report,
    evaluate_or_fail,
    reject_skeleton,
    score_entry_metrics,
    score_manifests,
)


def test_reject_skeleton():
    with pytest.raises(Plan051ScoreError):
        reject_skeleton({"mode": "catalog-skeleton", "critical_count": 0})
    with pytest.raises(Plan051ScoreError):
        evaluate_or_fail(
            {
                "mode": "catalog-skeleton",
                "critical_count": 0,
                "hard_term_hit_rate": 1.0,
                "forbidden_translation_count": 0,
                "digit_unit_doi_ref_pass_rate": 1.0,
            }
        )


def test_digit_drift_fails_evaluate():
    m = score_entry_metrics(qc_codes=["TABLE_DIGIT_DRIFT:r2c1"])
    assert m["critical_count"] >= 1
    report = aggregate_report(
        [{**m, "tags": ["real"], "class": "L", "entry_id": "L-x"}],
        model_id="mock",
    )
    assert report["mode"] == "full-retranslate"
    assert evaluate_baseline_report(report, load_thresholds()) == "fail"


def test_clean_pass_with_glossary():
    m = score_entry_metrics(
        qc_codes=[],
        source_text="Patient received tralokinumab 300 mg.",
        target_text="患者接受了曲罗芦单抗 300 mg。",
        glossary={"tralokinumab": "曲罗芦单抗"},
        forbidden=["假药"],
    )
    assert m["critical_count"] == 0
    assert m["hard_term_hit_rate"] == 1.0
    report = aggregate_report(
        [{**m, "tags": ["real"], "class": "L", "entry_id": "L-clean"}],
        model_id="mock",
    )
    assert evaluate_or_fail(report) == "pass"


def test_score_manifests_sidecar_file(tmp_path: Path):
    qc = tmp_path / "x.imgtr.json"
    qc.write_text(
        json.dumps({"blocks": [{"object_qc": ["REF_GLUED_LEAK"]}]}),
        encoding="utf-8",
    )
    mans = [
        {
            "entry_id": "L-1",
            "class": "L",
            "tags": ["real"],
            "sidecar": [str(qc)],
            "source_text": "hello",
            "target_text": "你好",
        }
    ]
    report = score_manifests(mans, model_id="mock", glossary={})
    assert report["critical_count"] >= 1
    assert report["real_scored"] == 1
    assert report["per_class_real"]["L"] == 1


def test_synthetic_not_in_four_keys():
    mans = [
        {
            "entry_id": "S-1",
            "class": "R",
            "tags": ["synthetic"],
            "qc_codes": ["TABLE_DIGIT_DRIFT"],
            "source_text": "a",
            "target_text": "b",
        }
    ]
    report = score_manifests(mans, model_id="mock", glossary={})
    assert report["critical_count"] == 0
    assert report["synthetic_ran"] == 1
    assert report["real_scored"] == 0

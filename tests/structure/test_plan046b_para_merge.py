# SPDX-License-Identifier: MPL-2.0
"""PLAN-046b：段落合并补丁与药名漂移检测。"""
from __future__ import annotations

from pathlib import Path

from qyunslation.structure.text_sanitize import DRUG_NAME_DRIFT, detect_drug_name_drift


def test_drug_name_drift_with_source():
    codes = detect_drug_name_drift(
        "使用度普利尤单抗治疗",
        source_text="Patients received tralokinumab Q2W",
    )
    assert any(c.startswith(DRUG_NAME_DRIFT) for c in codes)
    assert "dupilumab" in codes[0]


def test_drug_name_no_drift_when_source_has_inn():
    codes = detect_drug_name_drift(
        "曲罗芦单抗有效",
        source_text="Tralokinumab was effective",
    )
    assert codes == []


def test_drug_name_multi_without_source():
    codes = detect_drug_name_drift("曲罗芦单抗与度普利尤单抗")
    assert len(codes) >= 2


def test_literature_min_scale_in_profile():
    import tomllib

    data = tomllib.loads(Path("scripts/doc_profiles.toml").read_text(encoding="utf-8"))
    assert float(data["literature"]["min_scale"]) == 0.8


def test_046b_patcher_exists():
    assert Path("scripts/apply-pdf2zh-046b-para-merge.py").is_file()
    svc = Path("scripts/pdf2zh.service").read_text(encoding="utf-8")
    assert "apply-pdf2zh-046b-para-merge.py" in svc

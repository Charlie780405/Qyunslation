# SPDX-License-Identifier: MPL-2.0
"""PLAN-045a：皮肤科/疗效终点词库与图片默认 merged 路径。"""
from __future__ import annotations

from pathlib import Path

from qyunslation.extensions import image_translate as it
from qyunslation.glossary.governance import load_glossary_csv, merge_by_priority

ROOT = Path(__file__).resolve().parents[2]
CLINICAL = ROOT / "glossaries" / "clinical-lifecycle.csv"


def test_endpoint_phrases_in_l1():
    entries = load_glossary_csv(
        CLINICAL, default_layer="clinical", curated_only=True, skip_junk=True
    )
    merged = merge_by_priority(entries)
    assert merged["clear or almost clear"] == "皮损完全清除或几乎清除"
    assert merged["clear/almost clear"] == "皮损完全清除或几乎清除"
    assert "皮损完全清除或几乎清除" in merged["IGA 0/1"]
    assert merged["tralokinumab"] == "曲罗芦单抗"
    assert merged["Q4W"].startswith("每 4 周一次")
    assert merged["Objectives"] == "目的"
    assert "clear" not in merged


def test_phrase_beats_bare_clear_on_apply():
    gloss = {
        "clear or almost clear": "皮损完全清除或几乎清除",
        "skin clear": "皮损完全清除",
    }
    out = it._apply_glossary(
        "Patients achieved clear or almost clear skin.",
        gloss,
    )
    assert "皮损完全清除或几乎清除" in out
    assert "皮肤清晰" not in out


def test_image_glossary_defaults_to_merged(monkeypatch):
    monkeypatch.setattr(it, "GLOSSARY_CSV", "")
    path = it._resolve_glossary_path()
    assert path is not None
    assert path.name == "merged.csv"
    gloss = it._load_glossary()
    assert gloss.get("clear or almost clear") == "皮损完全清除或几乎清除"
    assert "clear" not in gloss

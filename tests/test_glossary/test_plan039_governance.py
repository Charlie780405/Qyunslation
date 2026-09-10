# SPDX-License-Identifier: MPL-2.0
"""PLAN-039：术语治理单测。"""
from __future__ import annotations

from pathlib import Path

import pytest

from qyunslation.glossary.governance import (
    GlossaryEntry,
    build_merged_dict,
    is_junk_source,
    load_glossary_csv,
    merge_by_priority,
    write_glossary_csv,
)


def test_merge_org_beats_harvest():
    entries = [
        GlossaryEntry("GenScend", "金斯瑞", layer="harvest", status="curated"),
        GlossaryEntry("GenScend", "GenScend", layer="org", status="curated"),
    ]
    merged = merge_by_priority(entries)
    assert merged["GenScend"] == "GenScend"


def test_merge_org_beats_clinical():
    entries = [
        GlossaryEntry("CMC", "化学制造与控制", layer="clinical", src_lng="en"),
        GlossaryEntry("CMC", "CMC", layer="org", src_lng="en"),
    ]
    merged = merge_by_priority(entries)
    assert merged["CMC"] == "CMC"


def test_junk_sources():
    assert is_junk_source("Page 2")
    assert is_junk_source("Question 1")
    assert is_junk_source("September 18, 2026")
    assert not is_junk_source("GenScend")
    assert not is_junk_source("江苏景行生物医药有限公司")


def test_roundtrip_csv(tmp_path: Path):
    path = tmp_path / "t.csv"
    write_glossary_csv(
        path,
        [
            GlossaryEntry(
                "景行生物",
                "GenScend",
                src_lng="zh",
                tgt_lng="en",
                layer="org",
                domain="org",
                status="curated",
            )
        ],
    )
    loaded = load_glossary_csv(path, default_layer="org")
    assert len(loaded) == 1
    assert loaded[0].source == "景行生物"
    assert loaded[0].target == "GenScend"
    assert loaded[0].src_lng == "zh"


def test_build_merged_includes_genscend_seeds():
    root = Path(__file__).resolve().parents[2] / "glossaries"
    if not (root / "org-proper-nouns.csv").is_file():
        pytest.skip("org-proper-nouns.csv not yet created")
    merged = build_merged_dict(root)
    assert merged.get("景行生物") == "GenScend"
    assert merged.get("江苏景行生物医药有限公司") == "GenScend"
    assert "金斯瑞" not in {merged.get("GenScend"), merged.get("景行生物")}
    en = merged.get("Jiangsu GenScend Biopharma Co., Ltd.")
    assert en and "景行" in en

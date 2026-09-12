# SPDX-License-Identifier: MPL-2.0
"""PLAN-034d0：术语 SSOT 与 prompt 桥接。

历史对照（实现前）：load_glossary≈209（仅 clinical）vs build_merged_dict≈370；
全表 build_glossary_prompt≈9429 字符。实现后空 json 时条数应对齐，运行时按 chunk 命中过滤。
"""
from __future__ import annotations

from types import SimpleNamespace

from qyunslation.extensions import glossary_db
from qyunslation.extensions.glossary_db import (
    build_glossary_prompt,
    load_glossary,
)
from qyunslation.glossary.governance import build_merged_dict
from qyunslation.glossary.glossary import Glossary, _normalize_key
from qyunslation.glossary.ssot import apply_ssot_to_payload, merge_ssot_glossary


def test_load_glossary_matches_four_layer_merge(tmp_path, monkeypatch):
    # 空 json：条数应与 build_merged_dict 一致（历史 209 vs 370 已消除）
    monkeypatch.setattr(glossary_db, "DB_PATH", tmp_path / "glossary_db.json")
    glossary_db.PRESET_GLOSSARY.clear()
    merged = build_merged_dict()
    g = load_glossary()
    assert len(g) == len(merged)
    assert g.get("景行生物") == "GenScend"
    assert g.get("primary endpoint") == "主要终点"


def test_filter_and_prompt_hits_not_full_table():
    full = {
        "atopic dermatitis": "特应性皮炎",
        "primary endpoint": "主要终点",
        "景行生物": "GenScend",
    }
    # 人为拉长，模拟接近全表膨胀风险
    for i in range(200):
        full[f"term_{i}"] = f"译_{i}"
    prompt = build_glossary_prompt(full, text="Patients with atopic dermatitis only")
    assert "必须使用指定译法" in prompt
    assert "atopic dermatitis => 特应性皮炎" in prompt
    assert "primary endpoint" not in prompt
    assert "term_0" not in prompt
    assert len(prompt) < 500  # 远小于历史全表 ~9429


def test_build_glossary_prompt_no_hits():
    assert build_glossary_prompt({"hello": "你好"}, text="nothing matches") == ""


def test_normalize_key_merges_case():
    g = Glossary({"Hello": "你好"})
    g.update({"HELLO": "您好"})
    assert list(g.glossary_dict.keys()) == ["hello"]
    assert g.glossary_dict["hello"] == "你好"  # 不覆盖


def test_agent_update_glossary_no_case_dupes():
    # 与 markdown_agent / segments_agent 的 update_glossary_dict 同实现
    class Stub:
        glossary_dict = {"Hello": "你好"}

        def update_glossary_dict(self, update_dict):
            from qyunslation.glossary.glossary import Glossary

            gloss = Glossary(self.glossary_dict or {})
            gloss.update(update_dict or {})
            self.glossary_dict = gloss.glossary_dict

    s = Stub()
    s.update_glossary_dict({"HELLO": "您好", "World": "世界"})
    keys = list(s.glossary_dict.keys())
    assert "hello" in keys
    assert "HELLO" not in keys
    assert s.glossary_dict["hello"] == "你好"
    assert s.glossary_dict["world"] == "世界"


def test_merge_runtime_includes_ui_increment(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    from qyunslation.glossary.governance import GlossaryEntry, write_glossary_csv

    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "glossary_merge_runtime.py"
    spec = importlib.util.spec_from_file_location("glossary_merge_runtime", path)
    merge_rt = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["glossary_merge_runtime"] = merge_rt
    spec.loader.exec_module(merge_rt)

    ui = tmp_path / "ui-increment.csv"
    write_glossary_csv(
        ui,
        [
            GlossaryEntry(
                source="034d0_unique_term_xyz",
                target="〇三四零唯一译法",
                layer="session",
                status="curated",
            )
        ],
    )
    monkeypatch.setattr(merge_rt, "UI_INCREMENT", ui)
    monkeypatch.setattr(merge_rt, "HARVEST", tmp_path / "missing-harvest.csv")
    entries = merge_rt.build_merged_entries(include_harvest=False)
    sources = {e.source for e in entries}
    assert "034d0_unique_term_xyz" in sources


def test_apply_ssot_fills_empty_glossary_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_db, "DB_PATH", tmp_path / "glossary_db.json")
    glossary_db.PRESET_GLOSSARY.clear()
    payload = SimpleNamespace(glossary_dict=None, custom_prompt="user rules")
    apply_ssot_to_payload(payload)
    assert isinstance(payload.glossary_dict, dict)
    assert len(payload.glossary_dict) >= 100
    assert payload.custom_prompt == "user rules"  # 全表不得写入 custom_prompt
    assert "primary endpoint" in payload.glossary_dict or "primary endpoint".casefold() in {
        k.casefold() for k in payload.glossary_dict
    }


def test_apply_ssot_user_override(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_db, "DB_PATH", tmp_path / "glossary_db.json")
    glossary_db.PRESET_GLOSSARY.clear()
    payload = SimpleNamespace(
        glossary_dict={"primary endpoint": "用户自定义终点"},
        custom_prompt="",
    )
    apply_ssot_to_payload(payload)
    key = _normalize_key("primary endpoint")
    assert payload.glossary_dict[key] == "用户自定义终点"
    assert payload.custom_prompt == ""


def test_merge_ssot_counts():
    merged, n, ov = merge_ssot_glossary({"brand_new_034d0": "新词"})
    assert n >= 100
    assert "brand_new_034d0" in merged or _normalize_key("brand_new_034d0") in merged
    assert ov >= 1


def test_export_ui_increment_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_db, "DB_PATH", tmp_path / "glossary_db.json")
    glossary_db.PRESET_GLOSSARY.clear()
    out = tmp_path / "ui-increment.csv"
    glossary_db.save_glossary({"ui_only_term": "界面术语"})
    path = glossary_db.export_ui_increment_csv(out)
    text = path.read_text(encoding="utf-8")
    assert "ui_only_term" in text
    assert "session" in text

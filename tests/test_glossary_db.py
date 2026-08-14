# SPDX-License-Identifier: MPL-2.0
"""glossary_db 术语表知识库单元测试（纯本地，不调 Ollama）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import glossary_db
from glossary_db import PRESET_GLOSSARY, build_glossary_prompt, load_glossary, merge_glossary


def test_load_glossary_includes_preset():
    g = load_glossary()
    assert len(g) >= len(PRESET_GLOSSARY)
    assert g["atopic dermatitis"] == "特应性皮炎"
    assert g["placebo"] == "安慰剂"


def test_build_glossary_prompt_strong_instruction():
    prompt = build_glossary_prompt({"atopic dermatitis": "特应性皮炎"})
    assert "必须使用指定译法" in prompt
    assert "atopic dermatitis => 特应性皮炎" in prompt


def test_build_glossary_prompt_empty():
    assert build_glossary_prompt({}) == ""


def test_merge_glossary_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_db, "DB_PATH", tmp_path / "glossary_db.json")
    merged = merge_glossary({"test_term": "测试术语"})
    assert "test_term" in merged
    assert (tmp_path / "glossary_db.json").exists()
    # 持久化后重新加载应包含新术语
    assert "test_term" in load_glossary()


def test_save_glossary_excludes_unchanged_preset(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_db, "DB_PATH", tmp_path / "glossary_db.json")
    saved = glossary_db.save_glossary({"atopic dermatitis": "特应性皮炎", "new_term": "新术语"})
    assert "atopic dermatitis" not in saved  # 与预置一致，被排除
    assert saved["new_term"] == "新术语"  # 用户新术语保留

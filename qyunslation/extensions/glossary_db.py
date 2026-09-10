#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""术语表知识库：持久化 + 注入 + 合并（PLAN-039：预置改读 L1 CSV）。

机制：
  - L1 预置：glossaries/clinical-lifecycle.csv
  - 用户增量：glossary_db.json
  - 翻译时注入：custom_prompt 强指令

用法：
  from glossary_db import load_glossary, build_glossary_prompt, merge_glossary
"""
from __future__ import annotations

import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "glossary_db.json"
_CLINICAL_CSV = Path(__file__).resolve().parents[2] / "glossaries" / "clinical-lifecycle.csv"

# 兼容旧导入名：运行时从 CSV 填充；CSV 缺失时用最小回退
PRESET_GLOSSARY: dict[str, str] = {}


def _load_l1_preset() -> dict[str, str]:
    if not _CLINICAL_CSV.is_file():
        return {
            "atopic dermatitis": "特应性皮炎",
            "primary endpoint": "主要终点",
            "adverse event": "不良事件",
        }
    try:
        from qyunslation.glossary.governance import load_glossary_csv, merge_by_priority

        entries = load_glossary_csv(
            _CLINICAL_CSV, default_layer="clinical", curated_only=True, skip_junk=True
        )
        return merge_by_priority(entries)
    except Exception:
        return {}


def _ensure_preset() -> dict[str, str]:
    global PRESET_GLOSSARY
    if not PRESET_GLOSSARY:
        PRESET_GLOSSARY = _load_l1_preset()
    return PRESET_GLOSSARY


def _load_raw():
    if DB_PATH.exists():
        try:
            return json.loads(DB_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_glossary():
    """加载术语表（L1 预置 + 持久化合并，持久化优先覆盖预置）。"""
    merged = dict(_ensure_preset())
    merged.update(_load_raw())
    return merged


def save_glossary(glossary_dict):
    """保存术语表（不含预置，只存用户新增/修改的）。"""
    preset = _ensure_preset()
    user = {k: v for k, v in glossary_dict.items() if k not in preset or preset[k] != v}
    DB_PATH.write_text(json.dumps(user, ensure_ascii=False, indent=2), encoding="utf-8")
    return user


def merge_glossary(new_dict):
    """合并新术语（去重 + 新术语优先），返回合并后的完整术语表并持久化。"""
    merged = load_glossary()
    merged.update(new_dict)
    save_glossary(merged)
    return merged


def build_glossary_prompt(glossary_dict, to_lang="中文"):
    """生成 custom_prompt 强指令（注入翻译，要求严格遵守术语表）。"""
    if not glossary_dict:
        return ""
    lines = "\n".join(f"{k} => {v}" for k, v in sorted(glossary_dict.items()))
    return f"翻译时，以下术语必须使用指定译法，不得使用其他译法（这是硬性要求）：\n{lines}"


if __name__ == "__main__":
    g = load_glossary()
    preset = _ensure_preset()
    print(f"术语表共 {len(g)} 条（L1 预置 {len(preset)} + 用户新增 {len(g)-len(preset)}）")
    print(build_glossary_prompt(g)[:300])

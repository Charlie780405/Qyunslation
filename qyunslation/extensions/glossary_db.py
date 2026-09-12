#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""术语表知识库：持久化 + 注入 + 合并（PLAN-034d0：四层 SSOT + session 导出）。

机制：
  - 预置：build_merged_dict()（org/form/clinical/project）
  - 用户增量：glossary_db.json → glossaries/staging/ui-increment.csv
  - 翻译时：service 挂 SSOT；chunk 命中过滤后强指令注入

用法：
  from qyunslation.extensions.glossary_db import load_glossary, build_glossary_prompt, merge_glossary
"""
from __future__ import annotations

import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "glossary_db.json"
_GLOSSARIES_DIR = Path(__file__).resolve().parents[2] / "glossaries"
UI_INCREMENT_CSV = _GLOSSARIES_DIR / "staging" / "ui-increment.csv"
_FALLBACK_PRESET = {
    "atopic dermatitis": "特应性皮炎",
    "primary endpoint": "主要终点",
    "adverse event": "不良事件",
}

# 兼容旧导入名：运行时从四层 merge 填充；全缺时用最小回退
PRESET_GLOSSARY: dict[str, str] = {}


def _load_l1_preset() -> dict[str, str]:
    """PLAN-034d0：预置改为四层 curated（不再只读 clinical）。"""
    try:
        from qyunslation.glossary.governance import build_merged_dict

        out = build_merged_dict()
        if out:
            return out
    except Exception:
        pass
    return dict(_FALLBACK_PRESET)


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
    """加载术语表（四层预置 + 持久化合并，持久化优先覆盖预置）。"""
    merged = dict(_ensure_preset())
    merged.update(_load_raw())
    return merged


def export_ui_increment_csv(path: Path | None = None) -> Path:
    """把 glossary_db.json 写成 governance 格式 session CSV（034d0）。"""
    from qyunslation.glossary.governance import GlossaryEntry, write_glossary_csv

    dest = Path(path) if path is not None else UI_INCREMENT_CSV
    raw = _load_raw()
    entries = [
        GlossaryEntry(
            source=str(src).strip(),
            target=str(tgt).strip(),
            src_lng="",
            tgt_lng="zh",
            layer="session",
            domain="",
            sponsor="",
            status="curated",
            notes="glossary_db.json",
        )
        for src, tgt in raw.items()
        if str(src).strip() and str(tgt).strip()
    ]
    write_glossary_csv(dest, entries)
    return dest


def save_glossary(glossary_dict):
    """保存术语表（不含预置，只存用户新增/修改的）。"""
    preset = _ensure_preset()
    user = {k: v for k, v in glossary_dict.items() if k not in preset or preset[k] != v}
    DB_PATH.write_text(json.dumps(user, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        export_ui_increment_csv()
    except Exception:
        pass
    return user


def merge_glossary(new_dict):
    """合并新术语（去重 + 新术语优先），返回合并后的完整术语表并持久化。"""
    merged = load_glossary()
    merged.update(new_dict)
    save_glossary(merged)
    return merged


def filter_glossary_hits(glossary_dict: dict[str, str] | None, text: str) -> dict[str, str]:
    """按 chunk 文本命中过滤；避免全表 ~9429 字符注入。"""
    if not glossary_dict or not text:
        return {}
    hay = text.casefold()
    return {
        src: dst
        for src, dst in glossary_dict.items()
        if src and src.casefold() in hay
    }


def build_glossary_prompt(glossary_dict, to_lang="中文", text: str | None = None):
    """生成 custom_prompt 强指令。

    text 非空时只渲染命中项（运行时路径）；text 为 None 时全表（仅 CLI/测试对照）。
    """
    if not glossary_dict:
        return ""
    items = filter_glossary_hits(glossary_dict, text) if text is not None else glossary_dict
    if not items:
        return ""
    lines = "\n".join(f"{k} => {v}" for k, v in sorted(items.items()))
    return f"翻译时，以下术语必须使用指定译法，不得使用其他译法（这是硬性要求）：\n{lines}"


if __name__ == "__main__":
    g = load_glossary()
    preset = _ensure_preset()
    print(f"术语表共 {len(g)} 条（预置 {len(preset)} + 用户新增 {len(g)-len(preset)}）")
    print(build_glossary_prompt(g)[:300])

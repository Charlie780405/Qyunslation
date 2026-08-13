#!/usr/bin/env python3
"""术语表知识库：持久化 + 注入 + 合并（阶段 3「越用越准」）。

机制：
  - 术语表库持久化在 glossary_db.json（{源术语: 标准译文}）
  - 翻译时注入：custom_prompt 强指令（已验证模型遵守"必须使用指定译法"）
  - 术语积累：merge_glossary 合并去重；用户可人工审定增删
  - 医学术语预置：PRESET_GLOSSARY（可扩展）

用法：
  from glossary_db import load_glossary, build_glossary_prompt, merge_glossary
"""
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "glossary_db.json"

# 预置医学术语（AD/自免领域常用，可不断扩充）
PRESET_GLOSSARY = {
    "atopic dermatitis": "特应性皮炎",
    "eczema": "湿疹",
    "pruritus": "瘙痒",
    "erythema": "红斑",
    "placebo": "安慰剂",
    "randomized": "随机",
    "double-blind": "双盲",
    "primary endpoint": "主要终点",
    "secondary endpoint": "次要终点",
    "adverse event": "不良事件",
    "serious adverse event": "严重不良事件",
    "informed consent": "知情同意",
    "inclusion criteria": "纳入标准",
    "exclusion criteria": "排除标准",
    "open-label": "开放标签",
    "extension study": "扩展研究",
    "maintenance therapy": "维持治疗",
    "T-cell activation": "T细胞活化",
    "monoclonal antibody": "单克隆抗体",
    "subcutaneous injection": "皮下注射",
    "dose escalation": "剂量递增",
    "efficacy": "疗效",
    "safety": "安全性",
    "tolerability": "耐受性",
}


def _load_raw():
    if DB_PATH.exists():
        try:
            return json.loads(DB_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_glossary():
    """加载术语表（预置 + 持久化合并，持久化优先覆盖预置）。"""
    merged = dict(PRESET_GLOSSARY)
    merged.update(_load_raw())
    return merged


def save_glossary(glossary_dict):
    """保存术语表（不含预置，只存用户新增/修改的）。"""
    user = {k: v for k, v in glossary_dict.items() if k not in PRESET_GLOSSARY or PRESET_GLOSSARY[k] != v}
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
    return (f"翻译时，以下术语必须使用指定译法，不得使用其他译法（这是硬性要求）：\n{lines}")


if __name__ == "__main__":
    g = load_glossary()
    print(f"术语表共 {len(g)} 条（预置 {len(PRESET_GLOSSARY)} + 用户新增 {len(g)-len(PRESET_GLOSSARY)}）")
    print(build_glossary_prompt(g)[:300])

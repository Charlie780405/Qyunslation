# SPDX-License-Identifier: MPL-2.0
"""PLAN-073c：按任务 model_snapshot 生成 pdf2zh 运行时配置。"""
from __future__ import annotations

import os
import re
from typing import Any


def _replace_toml_value(content: str, key: str, value: str, *, section: str | None = None) -> str:
    pattern = rf'(?m)^(\s*{re.escape(key)}\s*=\s*).*$'
    replacement = rf'\1"{value}"'
    if section:
        block = _section_block(content, section)
        if block is None:
            return content
        updated = re.sub(pattern, replacement, block)
        return content.replace(block, updated)
    return re.sub(pattern, replacement, content, count=1)


def _section_block(content: str, section: str) -> str | None:
    match = re.search(rf"(?ms)^\[{re.escape(section)}\]\s*\n(.*?)(?=^\[|\Z)", content)
    return match.group(0) if match else None


def _set_top_level_flag(content: str, key: str, enabled: bool) -> str:
    return re.sub(rf"(?m)^{re.escape(key)}\s*=.*$", f"{key} = {'true' if enabled else 'false'}", content, count=1)


def apply_model_snapshot(content: str, model_snapshot: dict[str, Any] | None) -> str:
    if not model_snapshot:
        return content
    provider = str(model_snapshot.get("provider") or "ollama").strip().casefold()
    model_id = str(model_snapshot.get("model_id") or "").strip()
    updated = content
    updated = _set_top_level_flag(updated, "ollama", provider == "ollama")
    updated = _set_top_level_flag(updated, "deepseek", provider == "deepseek")
    if provider == "deepseek":
        if model_id:
            updated = _replace_toml_value(updated, "deepseek_model", model_id, section="deepseek_detail")
        api_key = (
            (os.environ.get("QYUNSLATION_DEEPSEEK_API_KEY") or "").strip()
            or (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
        )
        if api_key:
            updated = _replace_toml_value(updated, "deepseek_api_key", api_key, section="deepseek_detail")
    elif model_id:
        updated = _replace_toml_value(updated, "ollama_model", model_id, section="ollama_detail")
    return updated

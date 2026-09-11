# SPDX-License-Identifier: MPL-2.0
"""PLAN-045c：正文 IL 标记消毒与叠印检测。"""
from __future__ import annotations

import os
import re

IL_MARKUP_LEAK = "IL_MARKUP_LEAK"
SOURCE_OVERLAY = "SOURCE_OVERLAY"

_SPAN_TAG_RE = re.compile(
    r"</?\s*span\b[^>]*>",
    re.IGNORECASE,
)
_STYLE_ID_RE = re.compile(
    r"\bstyle\s*=\s*['\"]?\s*id\s*:\s*\d+\s*['\"]?",
    re.IGNORECASE,
)
_LEAK_RE = re.compile(
    r"<\s*span\b|style\s*=\s*['\"]?\s*id\s*:",
    re.IGNORECASE,
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def strip_il_markup(text: str | None) -> str:
    """剥 BabelDOC IL 泄漏的 span / style=id 标记。"""
    raw = text or ""
    cleaned = _SPAN_TAG_RE.sub("", raw)
    cleaned = _STYLE_ID_RE.sub("", cleaned)
    # 容错：被拆开的 st yle=
    cleaned = re.sub(r"\bst\s*yle\s*=\s*['\"]?\s*id\s*:\s*\d+\s*['\"]?", "", cleaned, flags=re.I)
    return cleaned


def has_il_markup_leak(text: str | None) -> bool:
    return bool(_LEAK_RE.search(text or ""))


def sanitize_translated_text(text: str | None) -> tuple[str, list[str]]:
    """返回 (消毒后文本, QC 码列表)。消毒后仍含标记 → IL_MARKUP_LEAK。"""
    cleaned = strip_il_markup(text)
    codes: list[str] = []
    if has_il_markup_leak(cleaned):
        codes.append(IL_MARKUP_LEAK)
    return cleaned, codes


def detect_source_overlay(page_text: str) -> list[str]:
    """离线：同一页文本同时有大段中文与残留英文长词 → SOURCE_OVERLAY。

    生产默认 WARN；QYUNSLATION_PLAN045_STRICT=1 时由调用方升硬失败。
    """
    blob = page_text or ""
    if not _CJK_RE.search(blob):
        return []
    keep = {
        "iga",
        "easi",
        "ada",
        "nab",
        "nrs",
        "q2w",
        "q4w",
        "crswNP",
        "ecztra",
        "doi",
        "http",
        "https",
        "pdf",
        "table",
        "figure",
    }
    latin = [w for w in _LATIN_WORD_RE.findall(blob) if w.lower() not in keep]
    if len(latin) >= 8 and len(_CJK_RE.findall(blob)) >= 20:
        return [SOURCE_OVERLAY]
    return []

def overlay_is_hard_fail() -> bool:
    return os.environ.get("QYUNSLATION_PLAN045_STRICT", "0").lower() in {
        "1",
        "true",
        "on",
    }

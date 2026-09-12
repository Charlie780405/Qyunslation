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
_LATIN_RE = re.compile(r"[A-Za-z]")

# 模型无视 prompt 词库时的中文伪译；长词优先。
_CALQUES = (
    ("皮肤清晰或几乎清晰", "皮损完全清除或几乎清除"),
    ("皮肤清晰/几乎清晰", "皮损完全清除或几乎清除"),
    ("清晰或几乎清晰", "完全清除或几乎清除"),
    ("皮肤清晰", "皮损完全清除"),
    ("几乎清晰", "几乎清除"),
)

_GLOSS_PAIRS: list[tuple[str, str]] | None = None

# 译后强制只收短语/药名。Q2W、IGA 0/1 等缩写已在译文里，再展开会撑爆摘要行框。
# PLAN-047d：补中文数词嵌套形；另校正错误剂量口径与药名伪译。
_NESTED_DOSE = (
    (re.compile(r"每\s*2\s*周一次（每\s*2\s*周一次（Q2W））"), "每2周一次（Q2W）"),
    (re.compile(r"每\s*4\s*周一次（每\s*4\s*周一次（Q4W））"), "每4周一次（Q4W）"),
    (re.compile(r"每\s*两\s*周一次（每\s*2\s*周一次（Q2W））"), "每2周一次（Q2W）"),
    (re.compile(r"每\s*四\s*周一次（每\s*4\s*周一次（Q4W））"), "每4周一次（Q4W）"),
    (re.compile(r"每\s*四周一次（每\s*4\s*周一次（Q4W））"), "每4周一次（Q4W）"),
)

# 错误口径 → 标准口径（确定性；禁止「每周两次」这类自由表达）
_DOSE_CALQUES = (
    (re.compile(r"每周两次\s*[（(]\s*Q2W\s*[）)]"), "每2周一次（Q2W）"),
    (re.compile(r"每两周两次\s*[（(]\s*Q2W\s*[）)]"), "每2周一次（Q2W）"),
    (re.compile(r"每周四次\s*[（(]\s*Q4W\s*[）)]"), "每4周一次（Q4W）"),
)

_DRUG_CALQUES = (
    ("特罗金单抗", "曲罗芦单抗"),
    ("特罗芦单抗", "曲罗芦单抗"),
    ("曲罗金单抗", "曲罗芦单抗"),
)


def _force_pair_ok(src: str, tgt: str) -> bool:
    if src.casefold() == "tralokinumab":
        return True
    if not re.search(r"[a-z].*[a-z]", src):
        return False
    return (" " in src) or (len(src) >= 10)


def _en_zh_pairs() -> list[tuple[str, str]]:
    """clinical-lifecycle 的 en→zh；跳过 identity / 过短源，避免 SC 误伤 scale。"""
    global _GLOSS_PAIRS
    if _GLOSS_PAIRS is not None:
        return _GLOSS_PAIRS
    pairs: list[tuple[str, str]] = []
    try:
        from qyunslation.glossary.governance import GLOSSARIES_DIR, load_glossary_csv

        for entry in load_glossary_csv(
            GLOSSARIES_DIR / "clinical-lifecycle.csv",
            default_layer="clinical",
            curated_only=True,
            skip_junk=True,
        ):
            src, tgt = (entry.source or "").strip(), (entry.target or "").strip()
            if len(src) < 3 or src == tgt:
                continue
            if not _LATIN_RE.search(src) or not _CJK_RE.search(tgt):
                continue
            if not _force_pair_ok(src, tgt):
                continue
            pairs.append((src, tgt))
    except Exception:
        pairs = []
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    _GLOSS_PAIRS = pairs
    return _GLOSS_PAIRS


def _replace_term(text: str, src: str, tgt: str) -> str:
    if src.isascii() and _LATIN_RE.search(src):
        pat = r"(?<![A-Za-z0-9])" + re.escape(src) + r"(?![A-Za-z0-9])"
        return re.sub(pat, tgt, text, flags=re.I)
    return text.replace(src, tgt)


def apply_forced_terms(text: str | None) -> str:
    """译后强制：中文伪译校正 + 残留英文短语。不展开 Q2W 等缩写。"""
    raw = text or ""
    if not raw:
        return raw
    for src, tgt in _CALQUES:
        if src in raw:
            raw = raw.replace(src, tgt)
    for src, tgt in _DRUG_CALQUES:
        if src in raw:
            raw = raw.replace(src, tgt)
    for pat, repl in _DOSE_CALQUES:
        raw = pat.sub(repl, raw)
    for src, tgt in _en_zh_pairs():
        raw = _replace_term(raw, src, tgt)
    for pat, repl in _NESTED_DOSE:
        raw = pat.sub(repl, raw)
    # PLAN-047d：清掉 Fallback 残留拉丁碎片（如「发现gs」）
    raw = re.sub(r"(?<=[\u4e00-\u9fff])gs(?=[\u4e00-\u9fff]|\s|$|[，。；：])", "", raw)
    raw = re.sub(r"(^|\s)gs(?=[\u4e00-\u9fff])", r"\1", raw)
    return raw


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


DRUG_NAME_DRIFT = "DRUG_NAME_DRIFT"

# 常见单抗中文名 → 英文 INN（小写）
_MAB_ZH_EN: tuple[tuple[str, str], ...] = (
    ("曲罗芦单抗", "tralokinumab"),
    ("度普利尤单抗", "dupilumab"),
    ("乌帕替尼", "upadacitinib"),
    ("阿布昔替尼", "abrocitinib"),
    ("巴瑞替尼", "baricitinib"),
    ("来瑞替尼", "lebrikizumab"),
    ("奈马克珠单抗", "nemolizumab"),
)


def detect_drug_name_drift(doc_text: str | None, *, source_text: str | None = None) -> list[str]:
    """PLAN-046b：译文出现 glossary 外单抗中文名，且英文源未出现对应 INN → 告警。

    只告警不替换（同文可能合法提及他药）。
    """
    text = doc_text or ""
    src = (source_text or "").casefold()
    hits: list[str] = []
    for zh, en in _MAB_ZH_EN:
        if zh not in text:
            continue
        if en in src:
            continue
        # 源未提供时：只要出现 ≥2 个不同单抗中文名也告警
        hits.append(f"{zh}<->{en}")
    if not hits:
        return []
    if source_text is not None:
        # 有源文：仅回报源中不存在的
        return [DRUG_NAME_DRIFT + ":" + h for h in hits]
    # 无源文：至少两个不同单抗才告警
    if len(hits) >= 2:
        return [DRUG_NAME_DRIFT + ":" + h for h in hits]
    return []


def sanitize_translated_text(text: str | None) -> tuple[str, list[str]]:
    """返回 (消毒后文本, QC 码列表)。消毒后仍含标记 → IL_MARKUP_LEAK。"""
    cleaned = apply_forced_terms(strip_il_markup(text))
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

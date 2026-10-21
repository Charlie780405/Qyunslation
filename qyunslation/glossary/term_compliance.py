# SPDX-License-Identifier: MPL-2.0
"""已入库术语的合规自查：只给出"疑似不合规"标记与原因，不改任何数据。

规则来源：项目已有的入库排除规则（常用语 / 停用词）+ 结构性缺陷 + 候选自动批准产生的泛用短语。
是否清理由人决定（驳回可恢复）。
"""
from __future__ import annotations

import re
from typing import Any

from qyunslation.glossary.candidate_rules import should_exclude_from_termbase

REASONS: dict[str, str] = {
    "NO_SOURCE": "缺少源术语",
    "BROKEN_TARGET": "译名格式损坏",
    "TEST_JUNK": "测试残留数据",
    "PHRASE": "通用常用语（项目停用短语）",
    "DENYLIST": "通用常用语（项目停用词）",
    "GENERIC_PHRASE": "泛用短语（候选批准入库，无药物/靶点/缩写特征）",
}

_CANDIDATE_PREFIX = "document_term_candidate:"
_GENERIC = re.compile(r"^[a-z][a-z\-\u2011\s/]*$")
_DRUGISH = re.compile(r"(mab|nib|cept|tinib|ciclib|stat|vir)$", re.IGNORECASE)
_BROKEN_TARGET = re.compile(r"^[、，。,.]")
_JUNK_HASH = re.compile(r"\b[0-9a-f]{8,12}\b")
# 这些类型的候选需要固定译名，不按泛用短语处理。
_KEEP_TYPES = frozenset(
    {"药物", "drug", "target", "受体", "生物标志物", "细胞类型", "通路", "监管机构或学会", "方案名", "专业缩写"}
)


def assess_concept(
    source: str | None,
    target: str | None,
    *,
    do_not_translate: bool = False,
    evidence: str | None = None,
    term_type: str | None = None,
) -> dict[str, str] | None:
    """返回 ``{"code", "label"}``；合规返回 ``None``。"""
    src = (source or "").strip()
    tgt = (target or "").strip()
    from_candidate = (evidence or "").startswith(_CANDIDATE_PREFIX)

    code: str | None = None
    if not src:
        code = "NO_SOURCE"
    elif _BROKEN_TARGET.match(tgt):
        code = "BROKEN_TARGET"
    elif from_candidate and _JUNK_HASH.search(src):
        code = "TEST_JUNK"
    else:
        excluded, reason = should_exclude_from_termbase(src)
        if excluded and reason in {"PHRASE", "DENYLIST"}:
            code = reason
        elif (
            from_candidate
            and not do_not_translate
            and _GENERIC.match(src)
            and len(src.split()) <= 4
            and (term_type or "").strip() not in _KEEP_TYPES
            and not _DRUGISH.search(src)
        ):
            code = "GENERIC_PHRASE"
    if code is None:
        return None
    return {"code": code, "label": REASONS[code]}


SAME_SOURCE_LABELS: dict[str, str] = {
    "SAME_SOURCE_CONFLICT": "同源多译（同一源词对应不同译名，需人工统一）",
    "SAME_SOURCE_DUPLICATE": "同源重复（同一源词与同一译名重复入库，应合并为别名）",
}


def normalize_match_key(text: str | None) -> str:
    """大小写、标点、空白不敏感的比对键：'Co., Ltd.' 与 'Co. Ltd.' 得到同一结果。"""
    return re.sub(r"[\W_]+", " ", (text or "").lower()).strip()


def same_source_flags(rows: list[tuple[str, str | None, str | None]]) -> dict[str, dict[str, str]]:
    """rows: (concept_id, 优选源术语, 优选译名)。同一比对键下多个词条时打标，只标记不改数据。"""
    groups: dict[str, list[tuple[str, str]]] = {}
    for concept_id, source, target in rows:
        key = normalize_match_key(source)
        tgt = (target or "").strip()
        if key and tgt:
            groups.setdefault(key, []).append((concept_id, tgt))
    flags: dict[str, dict[str, str]] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        code = "SAME_SOURCE_CONFLICT" if len({t for _, t in members}) > 1 else "SAME_SOURCE_DUPLICATE"
        for concept_id, _ in members:
            flags[concept_id] = {"code": code, "label": SAME_SOURCE_LABELS[code]}
    return flags


def preferred_pair(terms: list[Any]) -> tuple[str, str]:
    """(英文优选源术语, 非英文优选译名)；缺失返回空串。"""
    source = next((t.text for t in terms if t.role == "preferred" and t.lang == "en"), "")
    target = next((t.text for t in terms if t.role == "preferred" and t.lang != "en"), "")
    return source or "", target or ""

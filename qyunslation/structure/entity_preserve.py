# SPDX-License-Identifier: MPL-2.0
"""PLAN-080e：人名、职务、机构名的"保留原文"判定与原因枚举（C4）。

用户决定（D1）：人名、职务、部门、机构名可以不译。此前只有 ``frontmatter`` 的作者/机构启发式在起作用，
含机构标记的职务（"Deputy Director, Office of New Drugs"）被保留，不含的（"Medical Director"、
"Regulatory Lead, IQVIA"）却被送去翻译，于是同一份名单一半译一半不译。

这里补上职务的识别，并给每个"保留"一个固定的原因，供 QA 区分"有意保留"和"漏译"：

* ``PERSON_NAME``：带学位/资质的人名（沿用 frontmatter 的作者判定）。
* ``JOB_TITLE``：职务（本模块）。
* ``ORG_NAME``：含机构标记的短行（沿用 frontmatter 的机构判定）。

不做"只有两三个首字母大写词"的纯人名判定：它和 "Clinical Pharmacology" 这类标题无法区分，
误保留标题的代价（标题没翻译）比人名被模型照常处理的代价大。
"""
from __future__ import annotations

import re

from .frontmatter import AFFILIATION, AUTHOR, _BODY_SENTENCE, classify_frontmatter_text

PERSON_NAME = "PERSON_NAME"
JOB_TITLE = "JOB_TITLE"
ORG_NAME = "ORG_NAME"
REASONS = (PERSON_NAME, JOB_TITLE, ORG_NAME)

_TITLE_NOUNS = frozenset(
    """director manager officer lead leader supervisor chief president head scientist pharmacist
    reviewer consultant specialist associate assistant coordinator founder co-founder cofounder
    counsel advisor adviser analyst engineer physician investigator statistician pharmacologist
    pharmacokineticist epidemiologist toxicologist chemist administrator executive partner professor
    fellow representative secretary treasurer chairman chairperson owner cmo ceo coo cfo cto vp svp evp""".split()
)
_CONNECTORS = frozenset({"of", "and", "for", "to", "the", "in", "&", "at", "on"})
# 句子里常见的开头词：后面接职务也只是一句话（"Please contact the Regulatory Lead"）。
_SENTENCE_STARTERS = frozenset(
    {"please", "contact", "ask", "see", "refer", "send", "submit", "call", "email", "notify", "thank", "contacted"}
)
_MAX_WORDS = 14
_MAX_TITLE_WORDS = 9  # 第一段（逗号、斜杠、括号之前）的词数上限

_SEGMENT_SPLIT = re.compile(r"[,;/(]|\s[-–—]\s")
_WORD_OK = re.compile(r"^(?:[A-Z][A-Za-z0-9.'&-]*|[A-Z]{2,}[A-Za-z0-9&/-]*|&)$")


def _tokens(segment: str) -> list[str]:
    return [t for t in re.split(r"\s+", segment.strip()) if t]


def _looks_like_title_words(tokens: list[str]) -> bool:
    for token in tokens:
        bare = token.strip("()[]")
        if bare.lower() in _CONNECTORS:
            continue
        if not _WORD_OK.match(bare):
            return False
    return True


def is_job_title(text: str | None) -> bool:
    """整行是一个职务（可带 ", 机构"、"/ 部门缩写" 之类的后缀）。偏向不判定：拿不准就交给翻译。"""
    value = " ".join((text or "").split())
    if not value or len(value.split()) > _MAX_WORDS:
        return False
    if value.endswith((".", ":", "?", "!", ";")) and not re.search(r"\b(?:Inc|Ltd|Co|Corp|Jr|Sr)\.$", value):
        return False
    if _BODY_SENTENCE.search(value):
        return False
    first_word = value.split()[0].lower().strip(",")
    if first_word in _SENTENCE_STARTERS:
        return False

    segments = [s for s in _SEGMENT_SPLIT.split(value) if s.strip()]
    if not segments:
        return False
    head = _tokens(segments[0])
    if not head or len(head) > _MAX_TITLE_WORDS:
        return False
    if not _looks_like_title_words(head):
        return False
    lowered = [t.strip("()[]").lower() for t in head]
    # 第一段以职务名词结尾："Medical Director"；或 "职务 of/for/to 对象"："Head of Biostatistics"
    ends_with_title = lowered[-1] in _TITLE_NOUNS
    title_then_connector = any(
        lowered[i] in _TITLE_NOUNS and lowered[i + 1] in {"of", "for", "to"}
        for i in range(len(lowered) - 1)
    )
    if not (ends_with_title or title_then_connector):
        return False
    # 其余段只允许是首字母大写的词、缩写、数字与连接词（机构、部门缩写）
    for segment in segments[1:]:
        if not _looks_like_title_words(_tokens(segment.replace(")", " "))):
            return False
    return True


def preserve_reason(text: str | None) -> str | None:
    """这段文字为什么应当保留原文；不应保留时返回 None。"""
    role = classify_frontmatter_text(text).role
    if role == AUTHOR:
        return PERSON_NAME
    if role == AFFILIATION:
        # "Deputy Director, Office of New Drugs" 带机构标记，但本质是职务
        return JOB_TITLE if is_job_title(text) else ORG_NAME
    if is_job_title(text):
        return JOB_TITLE
    return None

# SPDX-License-Identifier: MPL-2.0
"""PLAN-033h：BabelDOC 送 LLM 前消费参考文献 PRESERVE 策略。"""
from __future__ import annotations

import re

from .entity_preserve import is_job_title
from .frontmatter import AFFILIATION, AUTHOR, classify_frontmatter_text
from .references import (
    is_citation_block,
    is_citation_entry,
    is_reference_entry,
    is_reference_heading,
    is_section_break,
)

# PLAN-080a：[n] 形式在正文中几乎不出现，可以不等参考文献标题直接保留。
# "n. xxx" 与 "n xxx" 形式在正文中很常见（如监管信函的编号问题），只能在参考文献区内保留。
_BRACKET_ENTRY_RE = re.compile(r"^\s*\[\d+\]\s*\S")


class ReferencePreserveGate:
    """按阅读顺序跟踪参考文献区。标题本身也 PRESERVE。"""

    def __init__(self) -> None:
        self.in_references = False

    def should_preserve(self, text: str) -> bool:
        if is_reference_heading(text):
            self.in_references = True
            return True
        if is_section_break(text):
            self.in_references = False
            return False
        return bool(self.in_references)


class LlmRequestSpy:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def record(self, text: str) -> None:
        self.requests.append(text)

    @property
    def reference_request_count(self) -> int:
        return sum(
            1
            for text in self.requests
            if is_reference_heading(text) or is_reference_entry(text)
        )


_GATE = ReferencePreserveGate()
_SPY: LlmRequestSpy | None = None


def reset_preserve_gate() -> None:
    global _GATE
    _GATE = ReferencePreserveGate()


def install_llm_spy(spy: LlmRequestSpy | None = None) -> LlmRequestSpy:
    global _SPY
    _SPY = spy or LlmRequestSpy()
    return _SPY


def current_llm_spy() -> LlmRequestSpy | None:
    return _SPY


def paragraph_is_preserved(text: str | None, gate: ReferencePreserveGate | None = None) -> bool:
    """这段文字送翻译前是否应当原样保留。

    ``gate`` 缺省用模块级的全局状态（BabelDOC 在单个子进程里按段落顺序调用）；Word/PPT 的分段逻辑
    每份文档传入自己的状态，避免并发的多份文档互相干扰。
    """
    gate = gate if gate is not None else _GATE
    blob = text or ""
    role = classify_frontmatter_text(blob).role
    if role in {AUTHOR, AFFILIATION} or is_job_title(blob):  # PLAN-080e：职务同样保留
        return True
    if _BRACKET_ENTRY_RE.match(blob) and not is_section_break(blob):
        return True
    # 标题缺失、写法不标准或 BabelDOC 的段落顺序不是阅读顺序时，期刊引文仍保留（PLAN-080）：
    # 单条引文看开头，合并成一个长段落的多条引文看密度，都不依赖全局状态。
    if is_citation_entry(blob) or is_citation_block(blob):
        return True
    # 编号段落只有在参考文献区内才是条目；否则会把正文的编号问题整段留成英文（PLAN-080a）。
    if gate.in_references and is_reference_entry(blob) and not is_section_break(blob):
        return True
    return gate.should_preserve(blob)


def filter_paragraphs_for_llm(texts: list[str], *, spy: LlmRequestSpy | None = None) -> list[str]:
    gate = ReferencePreserveGate()
    recorder = spy or _SPY
    kept: list[str] = []
    for text in texts:
        if (
            classify_frontmatter_text(text).role in {AUTHOR, AFFILIATION}
            or is_job_title(text)
            or bool(_BRACKET_ENTRY_RE.match(text))
            or is_citation_entry(text)
            or is_citation_block(text)
            or gate.should_preserve(text)
        ):
            continue
        kept.append(text)
        if recorder is not None:
            recorder.record(text)
    return kept


def title_is_usable_context(text: str | None) -> bool:
    blob = text or ""
    return (
        classify_frontmatter_text(blob).role not in {AUTHOR, AFFILIATION}
        and not is_job_title(blob)
        and not is_reference_heading(blob)
        and not is_reference_entry(blob)
    )

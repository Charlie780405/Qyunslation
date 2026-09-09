# SPDX-License-Identifier: MPL-2.0
"""PLAN-033h：BabelDOC 送 LLM 前消费参考文献 PRESERVE 策略。"""
from __future__ import annotations

from .references import is_reference_entry, is_reference_heading, is_section_break


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


def paragraph_is_preserved(text: str | None) -> bool:
    blob = text or ""
    if is_reference_heading(blob) or is_reference_entry(blob):
        return True
    return _GATE.should_preserve(blob)


def filter_paragraphs_for_llm(texts: list[str], *, spy: LlmRequestSpy | None = None) -> list[str]:
    gate = ReferencePreserveGate()
    recorder = spy or _SPY
    kept: list[str] = []
    for text in texts:
        if gate.should_preserve(text):
            continue
        kept.append(text)
        if recorder is not None:
            recorder.record(text)
    return kept


def title_is_usable_context(text: str | None) -> bool:
    blob = text or ""
    return not is_reference_heading(blob) and not is_reference_entry(blob)

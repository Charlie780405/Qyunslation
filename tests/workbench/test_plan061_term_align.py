# SPDX-License-Identifier: MPL-2.0
"""PLAN-061：实际译法确定性对齐 + LLM 建议不写幻觉。"""
from __future__ import annotations

from dataclasses import dataclass

from qyunslation.workbench.term_align import (
    MATCH_LLM,
    MATCH_NONE,
    MATCH_TERMBASE,
    MATCH_VERBATIM,
    AlignedTerm,
    align_observed,
    suggest_targets,
)


def test_align_prefers_termbase_then_verbatim_then_window():
    policy = {
        "terms": [
            {
                "source_term": "primary endpoint",
                "preferred_target": "主要终点",
                "hard_constraint": True,
            }
        ]
    }
    termbase = align_observed(
        "primary endpoint",
        source_context="The primary endpoint was met.",
        target_context="主要终点已达到。",
        policy=policy,
    )
    assert termbase.match_type == MATCH_TERMBASE
    assert termbase.observed_target == "主要终点"

    verbatim = align_observed(
        "300 mg",
        source_context="Patients received 300 mg every 2 weeks.",
        target_context="患者每两周接受 300 mg。",
        policy={},
    )
    assert verbatim.match_type == MATCH_VERBATIM
    assert verbatim.observed_target == "300 mg"

    none = align_observed(
        "tralokinumab",
        source_context="tralokinumab reduced lesions.",
        target_context="曲罗芦单抗减少皮损。",
        policy={},
    )
    assert none.match_type == MATCH_NONE
    assert none.observed_target == ""

    empty = align_observed(
        "ABC-101",
        source_context="ABC-101 was administered.",
        target_context="已给药。",
        policy={},
    )
    assert empty.match_type == MATCH_NONE
    assert empty.observed_target == ""


def test_suggest_targets_rejects_hallucinated_observed_and_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_TERM_SUGGEST", "1")
    calls = []

    @dataclass
    class FakeProvider:
        timeout: float = 30.0

        def translate(self, source: str, *, system: str | None = None) -> str:
            calls.append(source)
            return (
                '[{"source_term":"tralokinumab","observed_target":"幻觉译法",'
                '"suggested_target":"曲罗芦单抗","confidence":0.8}]'
            )

    aligned = AlignedTerm("tralokinumab", "", None, MATCH_NONE, 0.0)
    row = {
        "extracted": {"target_context": "患者接受曲罗芦单抗治疗。"},
        "aligned": aligned,
    }
    first = suggest_targets([row], provider=FakeProvider(), cache_dir=tmp_path)
    assert first["tralokinumab"].suggested_target == "曲罗芦单抗"
    assert first["tralokinumab"].observed_target == ""
    assert first["tralokinumab"].match_type == MATCH_LLM

    second = suggest_targets([row], provider=FakeProvider(), cache_dir=tmp_path)
    assert second["tralokinumab"].suggested_target == "曲罗芦单抗"
    assert len(calls) == 1


def test_suggest_targets_swallows_provider_errors(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_TERM_SUGGEST", "1")

    class Boom:
        def translate(self, source: str, *, system: str | None = None) -> str:
            raise RuntimeError("ollama down")

    aligned = AlignedTerm("tralokinumab", "", None, MATCH_NONE, 0.0)
    result = suggest_targets(
        [{"extracted": {"target_context": "患者接受治疗。"}, "aligned": aligned}],
        provider=Boom(),
    )
    assert result == {}

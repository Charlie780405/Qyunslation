# SPDX-License-Identifier: MPL-2.0
"""PLAN-062c：段落批次对齐只采纳译文中逐字存在的实际译法。"""
from __future__ import annotations

from dataclasses import dataclass

from qyunslation.workbench.term_align import (
    MATCH_LLM,
    MATCH_NONE,
    AlignedTerm,
    align_by_paragraph_batch,
)


def test_paragraph_batch_accepts_verbatim_observed_and_rejects_hallucination(tmp_path):
    @dataclass
    class FakeProvider:
        def translate(self, source: str, *, system: str | None = None) -> str:
            return (
                '[{"source_term":"tralokinumab","observed_target":"曲罗芦单抗",'
                '"suggested_target":"曲罗芦单抗","confidence":0.9},'
                '{"source_term":"IUA","observed_target":"环境类型关系有",'
                '"suggested_target":"IUA","confidence":0.2}]'
            )

    rows = [
        {
            "extracted": {
                "source_context": "tralokinumab reduced lesions.",
                "target_context": "曲罗芦单抗减少皮损。",
            },
            "aligned": AlignedTerm("tralokinumab", "", None, MATCH_NONE, 0.0),
        },
        {
            "extracted": {
                "source_context": "IUA appeared without context.",
                "target_context": "曲罗芦单抗减少皮损。",
            },
            "aligned": AlignedTerm("IUA", "", None, MATCH_NONE, 0.0),
        },
    ]
    found = align_by_paragraph_batch(rows, provider=FakeProvider(), cache_dir=tmp_path)
    assert found["tralokinumab"].observed_target == "曲罗芦单抗"
    assert found["tralokinumab"].match_type == MATCH_LLM
    assert found["IUA"].observed_target == ""
    assert found["IUA"].suggested_target == "IUA"

# SPDX-License-Identifier: MPL-2.0
"""PLAN-071h Task 1/2：确定性优先、外发前脱敏、失败不外发。"""
from __future__ import annotations

import json

import pytest

from qyunslation.workbench.term_align import (
    MATCH_LLM,
    MATCH_NONE,
    MATCH_TERMBASE,
    AlignedTerm,
    suggest_targets,
)


class RecordingProvider:
    def __init__(self, reply: str = "[]"):
        self.calls: list[dict] = []
        self.reply = reply

    def translate(self, payload: str, *, system: str = "") -> str:
        self.calls.append({"payload": payload, "system": system})
        return self.reply


@pytest.fixture(autouse=True)
def _enable_suggest(monkeypatch, tmp_path):
    monkeypatch.setenv("QYUNSLATION_TERM_SUGGEST", "1")
    monkeypatch.setenv("QYUNSLATION_TERM_SUGGEST_CACHE", str(tmp_path / "cache"))


def _row(source, match, *, target="", context=""):
    return {
        "aligned": AlignedTerm(
            source_term=source,
            observed_target=target,
            suggested_target=target or None,
            match_type=match,
            confidence=1.0 if match != MATCH_NONE else 0.0,
        ),
        "extracted": {"target_context": context},
    }


def test_exact_or_termbase_hit_never_calls_the_model(tmp_path):
    provider = RecordingProvider()
    out = suggest_targets(
        [_row("placebo", MATCH_TERMBASE, target="安慰剂", context="安慰剂组")],
        provider=provider,
        cache_dir=tmp_path,
    )
    assert out == {} and provider.calls == []


def test_only_unresolved_terms_reach_the_model(tmp_path):
    reply = json.dumps(
        [{"source_term": "wibble", "observed_target": "", "suggested_target": "威布尔", "confidence": 0.7}]
    )
    provider = RecordingProvider(reply)
    out = suggest_targets(
        [
            _row("placebo", MATCH_TERMBASE, target="安慰剂"),
            _row("wibble", MATCH_NONE, context="这是一个 wibble 的示例"),
        ],
        provider=provider,
        cache_dir=tmp_path,
    )
    assert len(provider.calls) == 1
    sent = json.loads(provider.calls[0]["payload"])
    assert [item["source_term"] for item in sent] == ["wibble"]
    assert out["wibble"].match_type == MATCH_LLM


def test_external_request_body_has_no_raw_identity(tmp_path):
    provider = RecordingProvider("[]")
    suggest_targets(
        [_row("wibble", MATCH_NONE, context="联系 Dr. Alice Smith alice@acme.com 关于 wibble")],
        provider=provider,
        cache_dir=tmp_path,
        classification="internal",
    )
    body = provider.calls[0]["payload"]
    assert "alice@acme.com" not in body and "Alice Smith" not in body
    assert "[EMAIL]" in body


def test_confidential_never_sends_anything(tmp_path):
    provider = RecordingProvider("[]")
    out = suggest_targets(
        [_row("wibble", MATCH_NONE, context="机密上下文 wibble")],
        provider=provider,
        cache_dir=tmp_path,
        classification="confidential",
    )
    assert out == {} and provider.calls == []

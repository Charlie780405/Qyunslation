# SPDX-License-Identifier: MPL-2.0
"""PLAN-062b：领域名词裁定三级短路与降级。"""
from __future__ import annotations

from qyunslation.glossary.candidate_rules import EXCLUDE_FRAGMENT, should_exclude_from_termbase
from qyunslation.glossary.term_screen import (
    DECISION_DOMAIN,
    DECISION_GENERIC,
    DECISION_NOISE,
    ScreenVerdict,
    screen_terms,
)
from qyunslation.workbench.evidence import BilingualTermEvidence, collect_abbrev_candidates, extract_term_pairs


class _FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def translate(self, source: str, *, system: str | None = None) -> str:
        self.calls += 1
        return (
            '[{"source_term":"EASI","decision":"domain_term","term_type":"scale","reason":"score"},'
            '{"source_term":"TSARTAI","decision":"noise","term_type":"general","reason":"ocr"}]'
        )


def test_numab_fragment_is_excluded():
    excluded, reason = should_exclude_from_termbase("numab")
    assert excluded is True
    assert reason == EXCLUDE_FRAGMENT


def test_ilumab_fragment_is_excluded():
    excluded, reason = should_exclude_from_termbase("ilumab")
    assert excluded is True
    assert reason == EXCLUDE_FRAGMENT


def test_university_and_bare_abbreviation_are_not_auto_extracted():
    rows = extract_term_pairs(
        [
            BilingualTermEvidence(
                source_text="University Hospital treated TSARTAI and tralokinumab.",
                target_text="大学医院使用曲罗芦单抗。",
            )
        ]
    )
    sources = {row["source_term"] for row in rows}
    assert "tralokinumab" in sources
    assert "University" not in sources
    assert "Hospital" not in sources
    assert "TSARTAI" not in sources
    assert "TSARTAI" in collect_abbrev_candidates(
        "University Hospital treated TSARTAI and tralokinumab."
    )


def test_screen_prefers_history_and_skips_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_TERM_SCREEN", "1")
    store = tmp_path / "decisions.csv"
    store.write_text(
        "source,decision,term_type,reason,model,ts,prompt_version\n"
        "EASI,domain_term,scale,cached,llm,2026-01-01,062-v1\n",
        encoding="utf-8",
    )
    provider = _FakeProvider()
    verdicts = screen_terms(
        ["EASI", "TSARTAI"],
        provider=provider,
        decisions_path=store,
        persist=False,
    )
    assert verdicts["EASI"].origin == "decisions_csv"
    assert verdicts["EASI"].decision == DECISION_DOMAIN
    assert provider.calls == 1
    assert verdicts["TSARTAI"].decision == DECISION_NOISE


def test_screen_degrades_when_disabled(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_TERM_SCREEN", "0")
    provider = _FakeProvider()
    verdicts = screen_terms(["FOO"], provider=provider, persist=False)
    assert verdicts["FOO"].decision == DECISION_GENERIC
    assert provider.calls == 0

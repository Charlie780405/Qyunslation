# SPDX-License-Identifier: MPL-2.0
"""PLAN-079 end to end: a real QA round, then the gate in legacy / shadow / enforce."""
from __future__ import annotations

import pytest
from test_plan071e_real_qa_gate import HEADERS, _make_client, _run_to_review

from qyunslation.persist.db import reset_engine

pytest.importorskip("pymupdf")


class _OneCandidateProvider:
    """The structured term model finds one ordinary word that is not in the approved lexicon."""

    def translate(self, source, *, system=None):
        return '[{"source_term": "adults", "term_type": "疾病", "recommended_target": "成人", "reason": "test"}]'


def _run(monkeypatch, tmp_path, mode: str):
    monkeypatch.setenv("QYUNSLATION_TERM_GATE_MODE", mode)
    client = _make_client(monkeypatch, tmp_path, translate=True)
    provider = _OneCandidateProvider()
    monkeypatch.setattr("qyunslation.gateway.provider.get_provider", lambda **_kwargs: provider)
    monkeypatch.setattr("qyunslation.gateway.provider.get_profile_provider", lambda *a, **k: provider)
    return client


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_an_ordinary_vocabulary_candidate_blocks_delivery_only_before_enforce(monkeypatch, tmp_path, mode):
    with _run(monkeypatch, tmp_path, mode) as client:
        run_id, state = _run_to_review(client, HEADERS, tmp_path, f"e2e-{mode}")
        assert state["quality_state"] == "review_ready", state["quality_state"]
        terms = client.get(f"/api/v1/translation-runs/{run_id}/term-candidates", headers=HEADERS).json()
        assert terms["unresolved"] >= 1, terms  # the candidate exists and is undecided in every mode
        run = client.get(f"/api/v1/translation-runs/{run_id}", headers=HEADERS).json()
        gate = run["formal_gate"]
        assert gate["term_gate_mode"] == mode
        assert gate["unresolved_term_count"] >= 1  # still reported for display
        if mode == "enforce":
            assert gate["passed"] is True and "unresolved_terms" not in gate["reasons"]
        else:
            assert gate["passed"] is False and "unresolved_terms" in gate["reasons"]
        shadow = (run["term_summary"] or {}).get("gate_shadow")
        if mode == "legacy":
            assert shadow is None  # nothing changes, nothing is recorded
        else:
            assert shadow["legacy_term_reasons"] == ["unresolved_terms"]
            assert shadow["new_term_reasons"] == []
            assert shadow["review_required"] == 0
    reset_engine()

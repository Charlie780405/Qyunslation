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


def test_one_reviewer_can_waive_a_garbled_text_blocker_with_a_reason(monkeypatch, tmp_path):
    """The reported case: a garbled-text hit the reviewer can see is not real. One person, written reason, audited."""
    from _plan078_flow import OWNER, REVIEWER, make_client, run_to_gate
    from test_plan078b_dispositions import _inject, _item, _post, _run

    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, state = run_to_gate(client, OWNER, tmp_path, "garbled-waiver")
        assert state["quality_state"] == "review_ready"
        (item_id,) = _inject(run_id, [("blocker", "TEXT_ENCODING_ARTIFACT", {"detectors": {"c0": ["U+0007"]}, "pages": [2]})])
        assert _run(client, run_id)["quality_state"] == "qa_blocked"
        waived = _post(client, run_id, item_id, REVIEWER, "grant_waiver", "页面上读不出乱码，内容可以接受")
        assert waived.status_code == 200, waived.text
        assert _item(client, run_id, item_id)["status"] == "waived"
        body = _run(client, run_id)
        assert body["quality_state"] == "review_ready" and body["formal_gate"]["qa_blockers"] == 0
        # the reason is mandatory and audited
        short = _post(client, run_id, item_id, REVIEWER, "revoke_waiver", "太短")
        assert short.status_code == 422
    reset_engine()


def test_a_garbled_text_item_stored_as_c1_before_the_change_is_waivable_without_a_recheck(monkeypatch, tmp_path):
    """The task already at the gate keeps its stored class C1; the reclassification must still apply to it."""
    from sqlalchemy import select

    from _plan078_flow import OWNER, REVIEWER, make_client, run_to_gate
    from qyunslation.persist import db as persist_db
    from qyunslation.persist.models import QaItem
    from test_plan078b_dispositions import _inject, _item, _post

    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, _ = run_to_gate(client, OWNER, tmp_path, "garbled-legacy-class")
        (item_id,) = _inject(run_id, [("blocker", "TEXT_ENCODING_ARTIFACT", {"pages": [2]})])
        with persist_db.SessionLocal() as session:
            session.scalar(select(QaItem).where(QaItem.id == item_id)).rule_class = "C1"  # as stored by the old registry
            session.commit()
        shown = _item(client, run_id, item_id, REVIEWER)
        assert shown["rule_class"] == "C2" and "grant_waiver" in shown["allowed_dispositions"]
        assert _post(client, run_id, item_id, REVIEWER, "grant_waiver", "页面上读不出乱码，内容可以接受").status_code == 200
    reset_engine()


def test_a_blocker_comes_with_ways_out_limited_to_what_this_person_can_run(monkeypatch, tmp_path):
    from _plan078_flow import OWNER, REVIEWER, make_client, run_to_gate
    from test_plan078b_dispositions import _inject, _item

    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, _ = run_to_gate(client, OWNER, tmp_path, "remedies")
        garbled, term = _inject(run_id, [
            ("blocker", "TEXT_ENCODING_ARTIFACT", {"pages": [2]}),
            ("blocker", "TERM_HIGH_RISK_CONFLICT", {"concept_id": "c1", "expected": "度普利尤单抗", "source_term": "dupilumab"}),
        ])
        reviewer = {r["id"]: r for r in _item(client, run_id, garbled, REVIEWER)["remedies"]}
        assert reviewer["waive"]["action"] == "grant_waiver" and len(reviewer["waive"]["reason"]) >= 10
        assert reviewer["waive"]["recommended"] is True and "revise" in reviewer
        # the submitter alone may not waive: that option is simply not offered, the rest still is
        submitter = {r["id"] for r in _item(client, run_id, garbled, OWNER)["remedies"]}
        assert "waive" not in submitter and "revise" in submitter
        # a term conflict leads to the vocabulary workbench with the term already named
        term_remedies = {r["id"]: r for r in _item(client, run_id, term, REVIEWER)["remedies"]}
        assert term_remedies["termbase"]["search"] == "dupilumab" and term_remedies["termbase"]["recommended"] is True
    reset_engine()


def test_a_confirmer_clears_a_false_positive_on_a_critical_fact_without_a_second_person(monkeypatch, tmp_path):
    """Reported: 'I checked it, it is a false positive' left the blocker in place. Now a confirmer finishes it alone, marked."""
    from sqlalchemy import select

    from _plan078_flow import OWNER, make_client, run_to_gate
    from qyunslation.persist import db as persist_db
    from qyunslation.persist.models import QaDisposition
    from test_plan078b_dispositions import ADMIN, REVIEWER, _inject, _item, _post, _run

    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, _ = run_to_gate(client, OWNER, tmp_path, "self-confirm")
        (item_id,) = _inject(run_id, [("blocker", "LITERAL_MISSING_IND", {"kind": "ind", "missing": ["IND 123456"]})])

        # a confirmer is offered the one-step path; a plain reviewer is not
        by_id = {r["id"]: r for r in _item(client, run_id, item_id, ADMIN)["remedies"]}
        assert by_id["false_positive"]["then"] == "confirm_false_positive"
        reviewer_fp = next(r for r in _item(client, run_id, item_id, REVIEWER)["remedies"] if r["id"] == "false_positive")
        assert "then" not in reviewer_fp

        assert _post(client, run_id, item_id, ADMIN, "report_false_positive", "核对原文第3页后确认编号完整保留").status_code == 200
        # while it waits, the confirmer is shown what to do next; the reviewer is told who can confirm
        pending = {r["id"]: r for r in _item(client, run_id, item_id, ADMIN)["remedies"]}
        assert pending["confirm"]["recommended"] is True and pending["reject"]["action"] == "reject_false_positive"
        waiting = {r["id"]: r for r in _item(client, run_id, item_id, REVIEWER)["remedies"]}
        assert waiting["waiting"]["kind"] == "info" and "confirm" not in waiting

        confirmed = _post(client, run_id, item_id, ADMIN, "confirm_false_positive", "已复核原文和译文，同意这是检查误报，放行。")
        assert confirmed.status_code == 200, confirmed.text
        assert _item(client, run_id, item_id)["status"] == "false_positive_confirmed"
        body = _run(client, run_id)
        assert body["quality_state"] == "review_ready" and body["formal_gate"]["passed"] is True
        with persist_db.SessionLocal() as session:
            row = session.scalar(select(QaDisposition).where(QaDisposition.action == "confirm_false_positive"))
            assert row.self_review is True  # nobody else looked at it, and the record says so
        # a plain reviewer still cannot confirm anything
        (other,) = _inject(run_id, [("blocker", "LITERAL_MISSING_IND", {"kind": "ind", "missing": ["IND 654321"]})])
        assert _post(client, run_id, other, REVIEWER, "report_false_positive", "核对原文后确认编号完整").status_code == 200
        assert _post(client, run_id, other, REVIEWER, "confirm_false_positive", "我自己确认自己的反馈").status_code == 403
    reset_engine()

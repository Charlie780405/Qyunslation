"""PLAN-078b slice 3: dispositions are rule-bound, audited, append-only, and drive the delivery gate."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from _plan078_flow import ADMIN, OWNER, REVIEWER, make_client, run_to_gate
from qyunslation.api import v1 as api_v1_module
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import reset_engine
from qyunslation.persist.models import AuditEvent, QaDisposition, QaItem, TranslationRunRecord
from qyunslation.pipeline.qa import QaFinding, registry

pytest.importorskip("pymupdf")

TERM_ADMIN = {"X-Dev-User": "tadm", "X-Dev-Tenant": "pilot", "X-Dev-Role": "termbase_admin"}
REASON = "已逐项核对原文，确认属于版式差异"


def _inject(run_id, specs, *, quality="qa_blocked"):
    """Replace the run's verdict with hand-made findings (current items of one fake round)."""
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        for old in session.scalars(select(QaItem).where(QaItem.run_id == run_id)):
            old.is_current = False
        ids = []
        for severity, code, evidence in specs:
            finding = QaFinding(category="x", severity=severity, code=code, message="m", evidence=evidence)
            item = api_v1_module._new_qa_item(run, finding, round_id=None, trigger="test")
            session.add(item)
            session.flush()
            ids.append(item.id)
        blockers = sum(1 for s in specs if s[0] == "blocker")
        run.qa_summary = {"blocker": blockers, "unavailable": 0, "warning": len(specs) - blockers, "info": 0}
        run.quality_state = quality
        session.commit()
        return ids


def _post(client, run_id, item_id, headers, action, reason=REASON, **extra):
    return client.post(
        f"/api/v1/translation-runs/{run_id}/qa-items/{item_id}/dispositions",
        headers=headers,
        json={"action": action, "reason": reason, **extra},
    )


def _run(client, run_id, headers=ADMIN):
    return client.get(f"/api/v1/translation-runs/{run_id}", headers=headers).json()


def _item(client, run_id, item_id, headers=ADMIN):
    items = client.get(f"/api/v1/translation-runs/{run_id}/qa-items", headers=headers).json()["items"]
    return next(i for i in items if i["id"] == item_id)


@pytest.fixture()
def gated(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, state = run_to_gate(client, OWNER, tmp_path, "disp")  # submitted by "own"
        assert state["quality_state"] == "review_ready"
        yield client, run_id, tmp_path
    reset_engine()


# --- C1: critical facts cannot be waived --------------------------------------------------------


def test_critical_fact_cannot_be_waived_or_acknowledged(gated):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "AD_NUMBER_DRIFT", {"missing_in_target": ["45.2%"]})])
    for action in ("grant_waiver", "acknowledge"):
        response = _post(client, run_id, item_id, ADMIN, action)
        assert response.status_code == 422, (action, response.text)
        assert response.json()["detail"]["code"] == "ACTION_NOT_ALLOWED_FOR_CLASS"
    body = _run(client, run_id)
    assert body["quality_state"] == "qa_blocked" and body["formal_gate"]["passed"] is False


def test_false_positive_needs_a_second_person_to_confirm(gated):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "AD_NUMBER_DRIFT", {"missing_in_target": ["45.2%"]})])

    reported = _post(client, run_id, item_id, OWNER, "report_false_positive", "千分位写法不同，译文中数值一致")
    assert reported.status_code == 200, reported.text
    assert _item(client, run_id, item_id)["status"] == "false_positive_reported"
    still = _run(client, run_id)
    assert still["quality_state"] == "qa_blocked"  # a report alone changes nothing about delivery
    assert still["formal_gate"]["passed"] is False

    assert _post(client, run_id, item_id, OWNER, "confirm_false_positive").status_code == 403  # not a confirmer
    assert _post(client, run_id, item_id, REVIEWER, "confirm_false_positive").status_code == 403  # reviewers cannot

    # even a confirmer cannot confirm their own report
    own_report = _post(client, run_id, item_id, TERM_ADMIN, "report_false_positive", "我自己反馈的误报说明")
    assert own_report.status_code == 200
    assert _post(client, run_id, item_id, TERM_ADMIN, "confirm_false_positive").status_code == 409

    confirmed = _post(client, run_id, item_id, ADMIN, "confirm_false_positive", "核对原文表格后确认译文数值一致")
    assert confirmed.status_code == 200, confirmed.text
    assert _item(client, run_id, item_id)["status"] == "false_positive_confirmed"
    body = _run(client, run_id)
    assert body["quality_state"] == "review_ready"
    assert body["qa_summary"]["open_blocker"] == 0
    assert body["formal_gate"]["passed"] is True


def test_rejecting_a_false_positive_report_keeps_the_blocker(gated):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "UNTRANSLATED_BODY", {"output_kind": "mono"})])
    assert _post(client, run_id, item_id, OWNER, "report_false_positive", "这一页是图片，不需要翻译").status_code == 200
    assert _post(client, run_id, item_id, ADMIN, "reject_false_positive", "图片中含正文，需要翻译").status_code == 200
    assert _item(client, run_id, item_id)["status"] == "open"
    assert _run(client, run_id)["quality_state"] == "qa_blocked"


# --- C2 / C4: waivers by a reviewer, with a reason ---------------------------------------------------


def test_reviewer_waives_a_layout_issue_and_it_can_be_taken_back(gated):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "LOGO_MISSING", {"output_kind": "mono"})])
    assert _post(client, run_id, item_id, OWNER, "grant_waiver").status_code == 403  # submitter alone cannot
    waived = _post(client, run_id, item_id, REVIEWER, "grant_waiver")
    assert waived.status_code == 200, waived.text
    assert _item(client, run_id, item_id)["status"] == "waived"
    body = _run(client, run_id)
    assert body["quality_state"] == "review_ready" and body["formal_gate"]["passed"] is True
    assert "approve" in _run(client, run_id, REVIEWER)["allowed_actions"]

    revoked = _post(client, run_id, item_id, REVIEWER, "revoke_waiver", "复查后发现首页确实缺少印章")
    assert revoked.status_code == 200
    assert _item(client, run_id, item_id)["status"] == "open"
    assert _run(client, run_id)["quality_state"] == "qa_blocked"


def test_self_review_is_allowed_for_a_reviewer_but_marked(gated):
    client, run_id, _ = gated
    own_reviewer = {"X-Dev-User": "own", "X-Dev-Tenant": "pilot", "X-Dev-Role": "reviewer"}  # the submitter, now a reviewer
    (item_id,) = _inject(run_id, [("blocker", "TERM_HIGH_RISK_CONFLICT", {"concept_id": "c1", "expected": "度普利尤单抗"})])
    assert _post(client, run_id, item_id, own_reviewer, "grant_waiver").status_code == 200  # D3: allowed
    with persist_db.SessionLocal() as session:
        row = session.scalar(select(QaDisposition).where(QaDisposition.action == "grant_waiver"))
        assert row.self_review is True
        audit = session.scalars(select(AuditEvent).where(AuditEvent.action == "qa.disposition")).all()
        assert audit and audit[-1].extra["self_review"] is True
    assert _item(client, run_id, item_id)["disposition"]["self_review"] is True


# --- guard rails ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("reason", ["", "太短", "x" * 3])
def test_a_reason_is_required(gated, reason):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "LOGO_MISSING", {"output_kind": "mono"})])
    response = _post(client, run_id, item_id, REVIEWER, "grant_waiver", reason)
    assert response.status_code == 422


def test_stale_round_and_missing_items_are_conflicts(gated):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "LOGO_MISSING", {"output_kind": "mono"})])
    stale = _post(client, run_id, item_id, REVIEWER, "grant_waiver", expected_round_id="some-older-round")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "STALE_ROUND"
    missing = _post(client, run_id, "no-such-item", REVIEWER, "grant_waiver")
    assert missing.status_code == 404
    # a superseded item (an older round's) cannot be disposed of
    with persist_db.SessionLocal() as session:
        session.get(QaItem, item_id).is_current = False
        session.commit()
    assert _post(client, run_id, item_id, REVIEWER, "grant_waiver").status_code == 409


def test_no_dispositions_while_a_check_is_running_or_the_run_is_not_at_the_gate(gated):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "LOGO_MISSING", {"output_kind": "mono"})], quality="draft")
    response = _post(client, run_id, item_id, REVIEWER, "grant_waiver")
    assert response.status_code == 409 and response.json()["detail"]["code"] == "QA_CHECK_RUNNING"


def test_checker_trouble_has_nothing_to_dispose_of(gated):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("unavailable", "TERM_EXTRACTION_DEGRADED", {})], quality="qa_unavailable")
    response = _post(client, run_id, item_id, ADMIN, "grant_waiver")
    assert response.status_code == 422
    assert _run(client, run_id)["quality_state"] == "qa_unavailable"


def test_repeating_the_same_disposition_is_idempotent_and_history_is_append_only(gated):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "LOGO_MISSING", {"output_kind": "mono"})])
    first = _post(client, run_id, item_id, REVIEWER, "grant_waiver").json()
    again = _post(client, run_id, item_id, REVIEWER, "grant_waiver").json()
    assert first["disposition"]["id"] == again["disposition"]["id"]
    revoked = _post(client, run_id, item_id, REVIEWER, "revoke_waiver", "撤销例外以便重新核对该问题")
    assert revoked.status_code == 200, revoked.text
    regrant = _post(client, run_id, item_id, REVIEWER, "grant_waiver", "重新核对后再次授权例外")
    assert regrant.status_code == 200, regrant.text
    history = _item(client, run_id, item_id)["history"]
    assert [h["action"] for h in history] == ["grant_waiver", "revoke_waiver", "grant_waiver"]
    with persist_db.SessionLocal() as session:
        assert len(session.scalars(select(QaDisposition)).all()) == 3  # nothing overwritten or deleted


def test_item_payload_lists_what_this_caller_may_do(gated):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "AD_NUMBER_DRIFT", {"missing_in_target": ["1.5%"]})])
    owner_view = _item(client, run_id, item_id, OWNER)
    assert owner_view["allowed_dispositions"] == ["report_false_positive"]
    term_admin_view = _item(client, run_id, item_id, TERM_ADMIN)
    assert "confirm_false_positive" in term_admin_view["allowed_dispositions"]
    assert "grant_waiver" not in term_admin_view["allowed_dispositions"]


# --- delivery gate ------------------------------------------------------------------------------------


def test_unhandled_critical_issue_blocks_approval_and_formal_download(gated):
    client, run_id, _ = gated
    _inject(run_id, [("blocker", "AD_NUMBER_DRIFT", {"missing_in_target": ["45.2%"]})])
    denied = client.post(f"/api/v1/translation-runs/{run_id}/review-decision", headers=ADMIN, json={"decision": "approve"})
    assert denied.status_code == 409
    body = _run(client, run_id)
    assert body["formal_gate"]["qa_blockers"] == 1 and "qa_blockers" in body["formal_gate"]["reasons"]
    assert not [a for a in body["artifacts"] if a["formal_export"]]


def test_waivers_do_not_carry_over_to_different_output(gated, monkeypatch):
    client, run_id, _ = gated
    (item_id,) = _inject(run_id, [("blocker", "LOGO_MISSING", {"output_kind": "mono"})])
    with persist_db.SessionLocal() as session:  # pretend the round was checked against output "aaaa"
        from qyunslation.pipeline.qa import rounds

        row, _ = rounds.ensure_round(session, run_id, 1, trigger="test")
        row.status, row.artifact_digest = "succeeded", "a" * 64
        session.commit()
    assert _post(client, run_id, item_id, REVIEWER, "grant_waiver").status_code == 200
    assert _run(client, run_id)["quality_state"] == "review_ready"
    with persist_db.SessionLocal() as session:  # the output changes: a newer round against "bbbb"
        from qyunslation.pipeline.qa import rounds

        row, _ = rounds.ensure_round(session, run_id, 1, trigger="test")
        row.status, row.artifact_digest = "succeeded", "b" * 64
        run = session.get(TranslationRunRecord, run_id)
        api_v1_module._reconcile_with_dispositions(session, run)
        session.commit()
    after = _item(client, run_id, item_id)
    assert after["status"] == "open" and after["previous_disposition"] is True
    assert _run(client, run_id)["quality_state"] == "qa_blocked"


# --- batch ---------------------------------------------------------------------------------------------


def _batch(client, run_id, headers, action, item_ids, reason=REASON):
    return client.post(
        f"/api/v1/translation-runs/{run_id}/qa-dispositions/batch",
        headers=headers,
        json={"action": action, "reason": reason, "item_ids": item_ids},
    )


def test_batch_acknowledges_only_batchable_warnings_of_one_code(gated):
    client, run_id, _ = gated
    a, b = _inject(
        run_id,
        [
            ("warning", "LATIN_RESIDUE", {"output_kind": "mono"}),
            ("warning", "LATIN_RESIDUE", {"output_kind": "dual"}),
        ],
        quality="review_ready",
    )
    response = _batch(client, run_id, REVIEWER, "acknowledge", [a, b])
    assert response.status_code == 200, response.text
    assert [r["outcome"] for r in response.json()["results"]] == ["succeeded", "succeeded"]
    assert _item(client, run_id, a)["status"] == "acknowledged"


def test_batch_refuses_dose_mixed_codes_and_critical_items(gated):
    client, run_id, _ = gated
    dose1, dose2, residue, drift = _inject(
        run_id,
        [
            ("warning", "LITERAL_MISSING_DOSE", {"kind": "dose", "missing": ["10mg"]}),
            ("warning", "LITERAL_MISSING_DOSE", {"kind": "dose", "missing": ["20mg"]}),
            ("warning", "LATIN_RESIDUE", {"output_kind": "mono"}),
            ("blocker", "AD_NUMBER_DRIFT", {"missing_in_target": ["1%"]}),
        ],
    )
    not_batchable = _batch(client, run_id, REVIEWER, "acknowledge", [dose1, dose2])
    assert not_batchable.status_code == 422 and not_batchable.json()["detail"]["code"] == "NOT_BATCHABLE"
    mixed = _batch(client, run_id, REVIEWER, "acknowledge", [dose1, residue])
    assert mixed.status_code == 422 and mixed.json()["detail"]["code"] == "MIXED_CODES"
    critical = _batch(client, run_id, REVIEWER, "grant_waiver", [drift])
    assert critical.status_code == 422
    # dose warnings can still be acknowledged one at a time
    assert _post(client, run_id, dose1, REVIEWER, "acknowledge").status_code == 200


def test_batch_reports_each_item_and_checks_permissions_per_item(gated):
    client, run_id, _ = gated
    a, b = _inject(
        run_id,
        [("warning", "LATIN_RESIDUE", {"output_kind": "mono"}), ("warning", "LATIN_RESIDUE", {"output_kind": "dual"})],
        quality="review_ready",
    )
    other = {"X-Dev-User": "stranger", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"}
    denied = _batch(client, run_id, other, "acknowledge", [a, b])
    assert denied.status_code in {403, 404}
    partial = _batch(client, run_id, REVIEWER, "acknowledge", [a, "missing-id"])
    outcomes = {r["item_id"]: r["outcome"] for r in partial.json()["results"]}
    assert outcomes[a] == "succeeded" and outcomes["missing-id"] == "failed"
    assert len(partial.json()["results"]) == 2


# --- same fingerprint after a re-check ----------------------------------------------------------------


def test_confirmed_false_positive_survives_a_recheck_of_unchanged_output(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, state = run_to_gate(client, OWNER, tmp_path, "disp-recheck")
        assert state["quality_state"] == "qa_blocked"
        blockers = [i for i in client.get(f"/api/v1/translation-runs/{run_id}/qa-items", headers=ADMIN).json()["items"]
                    if i["severity"] == "blocker"]
        for item in blockers:
            assert _post(client, run_id, item["id"], OWNER, "report_false_positive", "这是图片页，无需翻译").status_code == 200
            assert _post(client, run_id, item["id"], ADMIN, "confirm_false_positive", "核对图片页后确认无需翻译").status_code == 200
        assert _run(client, run_id)["quality_state"] == "review_ready"

        client.post(f"/api/v1/translation-runs/{run_id}/requalify", headers=ADMIN)  # same output, same findings
        after = _run(client, run_id)
        assert after["quality_state"] == "review_ready"  # the confirmed verdict still stands
        statuses = {i["status"] for i in client.get(f"/api/v1/translation-runs/{run_id}/qa-items", headers=ADMIN).json()["items"]
                    if i["severity"] == "blocker"}
        assert statuses == {"false_positive_confirmed"}
    reset_engine()

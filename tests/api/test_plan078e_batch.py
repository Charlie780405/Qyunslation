"""PLAN-078e: batch actions report every task's outcome, check each one on its own, and replay safely."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from _plan078d_seed import ADMIN, OTHER, OTHER_TENANT, OWNER, REVIEWER, get_items, make_app, seed_run, tenant_id
from qyunslation.api import v1 as api_v1
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import reset_engine
from qyunslation.persist.models import PreflightRecord, RunBatchOperation, RunSelection, TranslationRunRecord

FAILED = {"status": "failed", "quality": "draft"}
RUNNING = {"status": "translating", "quality": "draft"}
REVIEW = {"status": "gated", "quality": "review_ready"}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    with make_app(monkeypatch, tmp_path) as current:
        yield current
    reset_engine()


def _seed(client, headers=OWNER, **spec):
    tenant = tenant_id(client, headers)
    spec.setdefault("actor", headers["X-Dev-User"])
    with persist_db.SessionLocal() as session:
        run = seed_run(session, tenant, **spec)
        if run.status in {"queued", "scanning", "translating", "rendering"}:
            run.heartbeat_at = datetime.now(timezone.utc)
        session.commit()
        return run.id


_key = iter(range(10_000))


def _batch(client, action, ids=None, headers=OWNER, key=None, **extra):
    body = {"action": action, **({"ids": ids} if ids is not None else {}), **extra}
    return client.post(
        "/api/v1/translation-runs/batch",
        headers={**headers, "Idempotency-Key": key or f"k{next(_key)}"},
        json=body,
    )


def _outcomes(response):
    assert response.status_code == 200, response.text
    return {item["id"]: (item["outcome"], item["reason_code"]) for item in response.json()["items"]}


def _row(run_id):
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        return None if run is None else (run.archived_at, run.deleted_at, run.status)


# --- request rules -------------------------------------------------------------------------------------------


def test_a_batch_needs_a_key_and_exactly_one_way_to_say_which_tasks(client):
    run_id = _seed(client, **FAILED)
    no_key = client.post("/api/v1/translation-runs/batch", headers=OWNER, json={"action": "archive", "ids": [run_id]})
    assert no_key.status_code == 400 and no_key.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    neither = _batch(client, "archive")
    assert neither.status_code == 422 and neither.json()["detail"]["code"] == "SELECTION_REQUIRED"
    both = _batch(client, "archive", [run_id], selection_token="x")
    assert both.status_code == 422 and both.json()["detail"]["code"] == "SELECTION_REQUIRED"
    too_many = _batch(client, "archive", [f"id{i}" for i in range(201)])
    assert too_many.status_code == 422 and too_many.json()["detail"]["code"] == "TOO_MANY_IDS"
    assert _batch(client, "explode", [run_id]).status_code == 422


# --- per-task outcomes ----------------------------------------------------------------------------------------


def test_a_mixed_batch_reports_each_task_and_one_failure_does_not_undo_the_others(client):
    ok = _seed(client, name="可归档", **FAILED)
    running = _seed(client, name="运行中", **RUNNING)
    already = _seed(client, name="已归档", archived=True, **FAILED)
    done = _outcomes(_batch(client, "archive", [ok, running, already, "no-such-id"]))
    assert done[ok] == ("succeeded", "")
    assert done[running] == ("failed", "ACTION_NOT_ALLOWED_IN_STATE")
    assert done[already] == ("skipped", "ALREADY_ARCHIVED")
    assert done["no-such-id"] == ("failed", "NOT_FOUND")
    assert _row(ok)[0] is not None and _row(running)[0] is None
    response = _batch(client, "archive", [ok, running], key="x1").json()
    assert (response["requested"], response["succeeded"], response["failed"], response["skipped"]) == (2, 0, 1, 1)
    assert {item["name"] for item in response["items"]} == {"可归档", "运行中"}


def test_each_task_is_authorised_on_its_own(client):
    mine = _seed(client, **FAILED)
    theirs = _seed(client, OTHER, **FAILED)
    # A reviewer sees both but may change neither; an admin may change both.
    reviewer = _outcomes(_batch(client, "archive", [mine, theirs], REVIEWER))
    assert reviewer == {mine: ("failed", "RUN_OWNER_REQUIRED"), theirs: ("failed", "RUN_OWNER_REQUIRED")}
    assert _row(mine)[0] is None
    # The submitter acts on their own task; the other task is invisible to them, whatever its state.
    own = _outcomes(_batch(client, "archive", [mine, theirs], OWNER))
    assert own == {mine: ("succeeded", ""), theirs: ("failed", "NOT_FOUND")}
    assert _outcomes(_batch(client, "archive", [theirs], ADMIN))[theirs] == ("succeeded", "")


def test_ids_from_another_tenant_or_nowhere_look_the_same(client):
    mine = _seed(client, **FAILED)
    other_tenant_run = _seed(client, OTHER_TENANT, **FAILED)
    outcomes = _outcomes(_batch(client, "archive", [other_tenant_run, "missing"]))
    assert outcomes[other_tenant_run] == outcomes["missing"] == ("failed", "NOT_FOUND")
    messages = {item["message"] for item in _batch(client, "archive", [other_tenant_run, "missing"]).json()["items"]}
    assert len(messages) == 1  # nothing tells the two apart
    assert _row(other_tenant_run)[0] is None and _row(mine)[0] is None


def test_unarchive_trash_and_restore_follow_the_same_rules(client):
    archived = _seed(client, archived=True, **FAILED)
    plain = _seed(client, **FAILED)
    running = _seed(client, **RUNNING)
    assert _outcomes(_batch(client, "unarchive", [archived, plain])) == {
        archived: ("succeeded", ""), plain: ("skipped", "NOT_ARCHIVED")
    }
    trashed = _outcomes(_batch(client, "trash", [archived, plain, running]))
    assert trashed == {archived: ("succeeded", ""), plain: ("succeeded", ""), running: ("failed", "RUN_STILL_EXECUTING")}
    assert get_items(client)["total"] == 1  # only the running one is left
    assert _outcomes(_batch(client, "trash", [plain]))[plain] == ("skipped", "ALREADY_IN_TRASH")
    assert _outcomes(_batch(client, "archive", [plain]))[plain] == ("failed", "RUN_IN_TRASH")
    restored = _outcomes(_batch(client, "restore_from_trash", [plain, running]))
    assert restored == {plain: ("succeeded", ""), running: ("skipped", "NOT_IN_TRASH")}
    assert get_items(client)["total"] == 2


def test_purge_is_admin_only_even_in_a_batch(client):
    run_id = _seed(client, **FAILED)
    assert _outcomes(_batch(client, "trash", [run_id]))[run_id][0] == "succeeded"
    denied = _batch(client, "purge", [run_id], OWNER)
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "ADMIN_REQUIRED"
    assert _row(run_id) is not None
    assert _outcomes(_batch(client, "purge", [run_id], ADMIN)) == {run_id: ("succeeded", "")}
    assert _row(run_id) is None


def test_a_purge_whose_files_cannot_be_removed_is_reported_as_failed_and_stays_in_the_bin(client, monkeypatch):
    good, bad = _seed(client, **FAILED), _seed(client, **FAILED)
    _batch(client, "trash", [good, bad])
    real = api_v1._remove_purged_files
    calls = {"n": 0}

    def flaky(files, dirs):
        calls["n"] += 1
        return ["locked"] if calls["n"] == 1 else real(files, dirs)

    monkeypatch.setattr(api_v1, "_remove_purged_files", flaky)
    outcomes = _outcomes(_batch(client, "purge", [bad, good], ADMIN))
    assert outcomes[bad] == ("failed", "PURGE_FILES_FAILED") and outcomes[good] == ("succeeded", "")
    assert _row(good) is None
    with persist_db.SessionLocal() as session:
        assert session.get(TranslationRunRecord, bad).purge_status == "failed"


def test_one_task_blowing_up_does_not_affect_the_rest(client, monkeypatch):
    first, second, third = (_seed(client, **FAILED) for _ in range(3))
    real = api_v1._move_task_to_trash

    def explode_for_second(session, identity, chain, now):
        if chain[-1].id == second:
            raise RuntimeError("disk full")
        return real(session, identity, chain, now)

    monkeypatch.setattr(api_v1, "_move_task_to_trash", explode_for_second)
    outcomes = _outcomes(_batch(client, "trash", [first, second, third]))
    assert outcomes == {first: ("succeeded", ""), second: ("failed", "INTERNAL_ERROR"), third: ("succeeded", "")}
    assert _row(second)[1] is None and _row(first)[1] is not None and _row(third)[1] is not None


# --- idempotency --------------------------------------------------------------------------------------------------


def test_the_same_key_replays_the_first_answer_without_acting_again(client):
    run_id = _seed(client, **FAILED)
    first = _batch(client, "archive", [run_id], key="same")
    assert first.json()["replayed"] is False and first.json()["succeeded"] == 1
    # Someone un-archives it; the replay must not archive it again, and must say what happened the first time.
    with persist_db.SessionLocal() as session:
        session.get(TranslationRunRecord, run_id).archived_at = None
        session.commit()
    again = _batch(client, "archive", [run_id], key="same")
    assert again.json()["replayed"] is True and again.json()["succeeded"] == 1
    assert _row(run_id)[0] is None
    reused = _batch(client, "trash", [run_id], key="same")
    assert reused.status_code == 422 and reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    with persist_db.SessionLocal() as session:
        assert session.scalars(select(RunBatchOperation)).all().__len__() == 1


def test_a_key_belongs_to_one_person(client):
    mine, theirs = _seed(client, **FAILED), _seed(client, OTHER, **FAILED)
    assert _batch(client, "archive", [mine], OWNER, key="shared").json()["replayed"] is False
    assert _batch(client, "archive", [theirs], OTHER, key="shared").json()["replayed"] is False


# --- "select all matches" -------------------------------------------------------------------------------------


def _select(client, headers=OWNER, **body):
    response = client.post("/api/v1/translation-runs/selection", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_selection_freezes_exactly_what_matched_when_it_was_made(client):
    matching = [_seed(client, name=f"协议 {i}", **FAILED) for i in range(5)]
    other = _seed(client, name="别的", **FAILED)
    selection = _select(client, q="协议")
    assert selection["count"] == 5 and selection["scope"] == "active"
    late = _seed(client, name="协议 迟到", **FAILED)  # created after the snapshot
    done = _batch(client, "archive", selection_token=selection["selection_token"])
    assert done.status_code == 200 and done.json()["succeeded"] == 5
    assert all(_row(run_id)[0] is not None for run_id in matching)
    assert _row(other)[0] is None and _row(late)[0] is None


def test_exclusions_and_stale_selections(client):
    runs = [_seed(client, **FAILED) for _ in range(4)]
    selection = _select(client)
    outcome = _outcomes(_batch(client, "archive", selection_token=selection["selection_token"], exclude_ids=[runs[0]]))
    assert runs[0] not in outcome and len(outcome) == 3
    # A task that started running after the snapshot is refused on its own; the rest still go through.
    again = _select(client, archived="all")
    with persist_db.SessionLocal() as session:
        session.get(TranslationRunRecord, runs[1]).archived_at = None
        session.get(TranslationRunRecord, runs[1]).status = "translating"
        session.get(TranslationRunRecord, runs[1]).heartbeat_at = datetime.now(timezone.utc)
        session.commit()
    trashed = _outcomes(_batch(client, "trash", selection_token=again["selection_token"]))
    assert trashed[runs[1]] == ("failed", "RUN_STILL_EXECUTING")
    assert sum(1 for value in trashed.values() if value[0] == "succeeded") == 3


def test_selection_tokens_expire_belong_to_one_person_and_match_the_action(client):
    _seed(client, **FAILED)
    selection = _select(client)
    token = selection["selection_token"]
    stranger = _batch(client, "archive", headers=OTHER, selection_token=token)
    assert stranger.status_code == 404 and stranger.json()["detail"]["code"] == "SELECTION_NOT_FOUND"
    mismatch = _batch(client, "restore_from_trash", selection_token=token)  # an active-task selection, a bin action
    assert mismatch.status_code == 422 and mismatch.json()["detail"]["code"] == "SELECTION_SCOPE_MISMATCH"
    with persist_db.SessionLocal() as session:
        session.get(RunSelection, token).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()
    expired = _batch(client, "archive", selection_token=token)
    assert expired.status_code == 410 and expired.json()["detail"]["code"] == "SELECTION_EXPIRED"


def test_a_selection_of_the_bin_is_for_bin_actions(client):
    run_id = _seed(client, **FAILED)
    _batch(client, "trash", [run_id])
    selection = _select(client, trash=True)
    assert selection["count"] == 1 and selection["scope"] == "trash"
    wrong = _batch(client, "archive", selection_token=selection["selection_token"])
    assert wrong.status_code == 422
    assert _outcomes(_batch(client, "restore_from_trash", selection_token=selection["selection_token"])) == {run_id: ("succeeded", "")}


def test_a_selection_that_is_too_large_is_refused_rather_than_cut_short(client, monkeypatch):
    monkeypatch.setattr(api_v1, "SELECTION_MAX", 3)
    for _ in range(4):
        _seed(client, **FAILED)
    response = client.post("/api/v1/translation-runs/selection", headers=OWNER, json={})
    assert response.status_code == 422 and response.json()["detail"]["code"] == "SELECTION_TOO_LARGE"


def test_a_selection_only_contains_what_the_caller_can_see(client):
    _seed(client, **FAILED)
    _seed(client, OTHER, **FAILED)
    assert _select(client, OWNER)["count"] == 1
    assert _select(client, OTHER)["count"] == 1
    assert _select(client, REVIEWER)["count"] == 2
    assert _select(client, OTHER_TENANT)["count"] == 0


def test_the_selection_uses_the_same_filters_as_the_list(client):
    for index in range(6):
        _seed(client, name=f"报告 {index}", **(FAILED if index % 2 else REVIEW))
    _seed(client, name="归档报告", archived=True, **FAILED)
    for params in ({"q": "报告"}, {"q": "报告", "lifecycle": ["failed"]}, {"archived": "archived"}, {"archived": "all"}):
        listed = get_items(client, **{key: (",".join(value) if isinstance(value, list) else value) for key, value in params.items()})
        assert _select(client, **params)["count"] == listed["total"], params


# --- scale --------------------------------------------------------------------------------------------------------------


def test_a_large_selection_is_processed_in_reasonable_time(client):
    tenant = tenant_id(client)
    with persist_db.SessionLocal() as session:
        for index in range(300):
            seed_run(session, tenant, name=f"批量 {index:03d}", **FAILED)
        session.commit()
    selection = _select(client)
    assert selection["count"] == 300
    started = time.perf_counter()
    done = _batch(client, "archive", selection_token=selection["selection_token"])
    elapsed = time.perf_counter() - started
    assert done.json()["succeeded"] == 300
    assert elapsed < 20, elapsed
    assert get_items(client)["total"] == 0 and get_items(client, archived="archived")["total"] == 300

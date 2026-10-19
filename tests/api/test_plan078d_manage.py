"""PLAN-078d: renaming is race-safe and every destructive action is authorised by task state and role."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from _plan078d_seed import ADMIN, OTHER, OWNER, REVIEWER, get_items, make_app, seed_run, tenant_id
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import reset_engine
from qyunslation.persist.models import PreflightRecord, TranslationRunRecord


@pytest.fixture()
def client(monkeypatch, tmp_path):
    with make_app(monkeypatch, tmp_path) as current:
        yield current
    reset_engine()


def _run(client, **spec):
    tenant = tenant_id(client)
    with persist_db.SessionLocal() as session:
        run = seed_run(session, tenant, **spec)
        if run.status in {"queued", "scanning", "translating", "rendering"}:
            run.heartbeat_at = datetime.now(timezone.utc)  # a live executor, so a read does not "lose" it
        session.commit()
        return run.id


def _patch(client, run_id, headers=OWNER, if_match=None, **body):
    extra = {"If-Match": str(if_match)} if if_match is not None else {}
    return client.patch(f"/api/v1/translation-runs/{run_id}", headers={**headers, **extra}, json=body)


def _detail(client, run_id, headers=OWNER):
    return client.get(f"/api/v1/translation-runs/{run_id}", headers=headers).json()


# --- rename ---------------------------------------------------------------------------------------------


def test_rename_trims_validates_and_bumps_the_version(client):
    run_id = _run(client, name="旧名字")
    start = _detail(client, run_id)["name_version"]
    ok = _patch(client, run_id, display_name="  新名字  ")
    assert ok.status_code == 200 and ok.json()["display_name"] == "新名字"
    assert ok.json()["name_version"] == start + 1
    same = _patch(client, run_id, display_name="新名字")
    assert same.status_code == 200 and same.json()["name_version"] == start + 1  # nothing changed, nothing bumped


@pytest.mark.parametrize(
    "name,code",
    [("", "NAME_REQUIRED"), ("   ", "NAME_REQUIRED"), ("x" * 121, "NAME_INVALID"), ("有控制\u0007字符", "NAME_INVALID"), ("换行\n名字", "NAME_INVALID")],
)
def test_invalid_names_are_refused_with_a_reason_and_change_nothing(client, name, code):
    run_id = _run(client, name="原名")
    response = _patch(client, run_id, display_name=name)
    assert response.status_code == 422 and response.json()["detail"]["code"] == code
    assert _detail(client, run_id)["display_name"] == "原名"


def test_duplicate_names_are_allowed(client):
    first, second = _run(client, name="同名"), _run(client, name="别的")
    assert _patch(client, second, display_name="同名").status_code == 200
    assert {i["display_name"] for i in get_items(client)["items"]} == {"同名"}


def test_the_original_file_name_can_be_restored_explicitly(client):
    run_id = _run(client, name="自定义", filename="original.pdf")
    reset = _patch(client, run_id, reset_display_name=True)
    assert reset.status_code == 200 and reset.json()["display_name"] is None
    assert reset.json()["filename"] == "original.pdf"


def test_a_stale_rename_is_a_conflict_that_shows_the_current_name(client):
    run_id = _run(client, name="v0")
    version = _detail(client, run_id)["name_version"]
    assert _patch(client, run_id, if_match=version, display_name="标签页A改的").status_code == 200
    stale = _patch(client, run_id, if_match=version, display_name="标签页B改的")
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["code"] == "NAME_CONFLICT" and detail["current_name"] == "标签页A改的"
    assert detail["current_version"] == version + 1
    assert _detail(client, run_id)["display_name"] == "标签页A改的"  # the loser did not overwrite
    retry = _patch(client, run_id, if_match=detail["current_version"], display_name="标签页B改的")
    assert retry.status_code == 200


def test_if_match_accepts_the_http_quoted_form_and_is_optional(client):
    run_id = _run(client, name="a")
    version = _detail(client, run_id)["name_version"]
    assert _patch(client, run_id, if_match=f'"{version}"', display_name="b").status_code == 200
    assert _patch(client, run_id, display_name="c").status_code == 200  # old clients send no header
    assert _patch(client, run_id, if_match="not-a-number", display_name="d").status_code == 400


def test_only_the_submitter_or_an_admin_can_rename(client):
    run_id = _run(client, name="x")
    assert _patch(client, run_id, headers=REVIEWER, display_name="y").status_code == 403
    assert _patch(client, run_id, headers=OTHER, display_name="y").status_code == 404
    assert _patch(client, run_id, headers=ADMIN, display_name="y").status_code == 200


# --- authorisation: the list of allowed actions is what the server enforces -----------------------------------

STATES = {
    "executing": {"status": "translating", "quality": "draft"},
    "qa_action": {"status": "gated", "quality": "qa_blocked"},
    "review": {"status": "gated", "quality": "review_ready"},
    "failed": {"status": "failed", "quality": "draft"},
    "interrupted": {"status": "interrupted", "quality": "draft"},
    "cancelled": {"status": "cancelled", "quality": "draft"},
    "completed": {"status": "succeeded", "quality": "approved"},
}
ACTORS = {"owner": OWNER, "reviewer": REVIEWER, "admin": ADMIN}
STATE_ACTORS = [(s, a) for s in STATES for a in ACTORS]


@pytest.mark.parametrize("state,actor", STATE_ACTORS)
def test_archive_rename_and_delete_follow_allowed_actions(client, state, actor):
    headers = ACTORS[actor]
    allowed = set(_detail(client, _run(client, **STATES[state]), headers)["allowed_actions"])

    def outcome(action):
        run_id = _run(client, **STATES[state])  # a fresh task per attempt
        if action == "rename":
            return _patch(client, run_id, headers=headers, display_name="改名").status_code
        if action == "archive":
            return _patch(client, run_id, headers=headers, archived=True).status_code
        return client.delete(f"/api/v1/translation-runs/{run_id}", headers=headers).status_code

    for action, success in (("rename", 200), ("archive", 200), ("delete", 204)):
        status = outcome(action)
        if action in allowed:
            assert status == success, (state, actor, action, status)
        else:
            assert status in {403, 409}, (state, actor, action, status)
            assert status == (403 if actor == "reviewer" else 409), (state, actor, action, status)


def test_a_running_task_cannot_be_archived_or_deleted_but_can_be_cancelled(client):
    run_id = _run(client, **STATES["executing"])
    refused = _patch(client, run_id, archived=True)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "ACTION_NOT_ALLOWED_IN_STATE"
    assert client.delete(f"/api/v1/translation-runs/{run_id}", headers=OWNER).status_code == 409
    assert client.post(f"/api/v1/translation-runs/{run_id}/cancel", headers=OWNER).status_code == 200


def test_cancelling_is_an_owner_or_admin_action(client):
    run_id = _run(client, **STATES["executing"])
    assert client.post(f"/api/v1/translation-runs/{run_id}/cancel", headers=REVIEWER).status_code == 403
    assert client.post(f"/api/v1/translation-runs/{run_id}/cancel", headers=ADMIN).status_code == 200


def test_restoring_from_the_archive_is_a_writer_action_and_idempotent(client):
    run_id = _run(client, **STATES["failed"], archived=True)
    assert client.post(f"/api/v1/translation-runs/{run_id}/restore", headers=REVIEWER).status_code == 403
    assert client.post(f"/api/v1/translation-runs/{run_id}/restore", headers=OWNER).status_code == 200
    assert client.post(f"/api/v1/translation-runs/{run_id}/restore", headers=OWNER).status_code == 200  # nothing left to restore
    assert _patch(client, run_id, archived=True).status_code == 200
    assert _patch(client, run_id, archived=True).status_code == 200  # already archived: no error


# --- a retry belongs to the submitter, not to whoever pressed the button -------------------------------------------


def test_a_reviewers_retry_stays_owned_by_the_original_submitter(client, tmp_path):
    run_id = _run(client, **STATES["failed"])
    with persist_db.SessionLocal() as session:  # the retry needs the original source to still be there
        run = session.get(TranslationRunRecord, run_id)
        source = tmp_path / "preflights" / session.get(PreflightRecord, run.preflight_id).storage_key
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"%PDF-1.4 seed")
    created = client.post(f"/api/v1/translation-runs/{run_id}/revisions", headers=REVIEWER, json={})
    assert created.status_code == 201, created.text
    new = created.json()
    assert new["actor_sub"] == "owner1"  # the task still belongs to its submitter
    assert new["settings"]["requested_by"] == "rev1"
    assert get_items(client, OWNER)["total"] == 1  # and the submitter sees it, as the newest version
    assert get_items(client, OWNER)["items"][0]["id"] == new["id"]

"""PLAN-078e: the recycle bin and the permanent purge keep files, evidence and shared sources safe."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from _plan078d_seed import ADMIN, OTHER, OTHER_TENANT, OWNER, REVIEWER, get_items, make_app, seed_run, tenant_id
from qyunslation.api import v1 as api_v1
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import reset_engine
from qyunslation.persist.models import (
    AuditEvent,
    PreflightRecord,
    ReviewDecision,
    TranslationArtifact,
    TranslationRunRecord,
)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    with make_app(monkeypatch, tmp_path) as current:
        yield current
    reset_engine()


def _seed(client, **spec):
    tenant = tenant_id(client)
    with persist_db.SessionLocal() as session:
        run = seed_run(session, tenant, **spec)
        if run.status in {"queued", "scanning", "translating", "rendering"}:
            run.heartbeat_at = datetime.now(timezone.utc)
        session.commit()
        return run.id


def _with_files(client, tmp_path, run_id):
    """Give a seeded task what a real one has on disk: source, an artifact, and a runner directory."""
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        preflight = session.get(PreflightRecord, run.preflight_id)
        source = tmp_path / "preflights" / preflight.storage_key
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"%PDF-1.4 source")
        artifact_key = f"{run.tenant_id}/{run.id}/out.docx"
        artifact_file = tmp_path / "artifacts" / artifact_key
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        artifact_file.write_bytes(b"translated")
        session.add(
            TranslationArtifact(
                run_id=run.id, tenant_id=run.tenant_id, artifact_key="out", kind="formal", file_type="docx",
                filename="out.docx", media_type="application/octet-stream", storage_key=artifact_key,
                size_bytes=10, sha256="0" * 64,
            )
        )
        work = tmp_path / "runs" / run.tenant_id / run.id / "generation-1"
        work.mkdir(parents=True, exist_ok=True)
        (work / "executor.log").write_text("log")
        session.add(
            ReviewDecision(
                run_id=run.id, generation=run.generation, decision="request_changes", user_id="rev1",
                comment="数字不一致", qa_snapshot={}, term_snapshot={}, model_snapshot={},
            )
        )
        session.commit()
        return {"source": source, "artifact": artifact_file, "work": work.parent}


def _rows(run_id=None):
    with persist_db.SessionLocal() as session:
        query = select(TranslationRunRecord)
        if run_id:
            query = query.where(TranslationRunRecord.id == run_id)
        return list(session.scalars(query))


def _trash(client, **params):
    return client.get("/api/v1/translation-runs", headers=OWNER, params={"trash": "true", **params}).json()


def _delete(client, run_id, headers=OWNER):
    return client.delete(f"/api/v1/translation-runs/{run_id}", headers=headers)


# --- moving to the bin -------------------------------------------------------------------------------------


def test_delete_moves_the_task_to_the_bin_and_touches_nothing_on_disk(client, tmp_path):
    run_id = _seed(client, name="方案", status="failed", quality="draft")
    files = _with_files(client, tmp_path, run_id)
    assert _delete(client, run_id).status_code == 204
    assert get_items(client)["items"] == [] and get_items(client)["total"] == 0
    assert client.get(f"/api/v1/translation-runs/{run_id}", headers=OWNER).status_code == 404
    assert all(path.exists() for path in files.values())
    binned = _trash(client)
    assert binned["total"] == 1
    row = binned["items"][0]
    assert row["id"] == run_id and row["deleted_at"] and row["trash_days_left"] == 30
    assert row["allowed_actions"] == ["restore_from_trash"]
    assert "purge" in client.get("/api/v1/translation-runs", headers=ADMIN, params={"trash": "true"}).json()["items"][0]["allowed_actions"]


def test_retention_is_configurable(client, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_TRASH_RETENTION_DAYS", "7")
    run_id = _seed(client, status="failed", quality="draft")
    assert _delete(client, run_id).status_code == 204
    assert _trash(client)["items"][0]["trash_days_left"] == 7


def test_a_running_task_cannot_be_deleted(client):
    run_id = _seed(client, status="translating", quality="draft")
    response = _delete(client, run_id)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "RUN_STILL_EXECUTING"
    assert _rows(run_id)[0].deleted_at is None


def test_deleting_a_task_takes_every_version_so_no_old_one_reappears(client):
    tenant = tenant_id(client)
    with persist_db.SessionLocal() as session:
        first = seed_run(session, tenant, name="协议", status="failed", quality="draft")
        second = seed_run(
            session, tenant, name="协议", status="gated", quality="review_ready", generation=2,
            preflight=session.get(PreflightRecord, first.preflight_id),
        )
        session.commit()
        first_id, second_id = first.id, second.id
    assert get_items(client)["items"][0]["id"] == second_id
    assert _delete(client, second_id).status_code == 204
    assert get_items(client)["total"] == 0  # the older version does not take its place
    assert {row.id for row in _rows() if row.deleted_at} == {first_id, second_id}
    assert _trash(client)["total"] == 1 and _trash(client)["items"][0]["id"] == second_id
    restored = client.post(f"/api/v1/translation-runs/{second_id}/restore-from-trash", headers=OWNER)
    assert restored.status_code == 200 and restored.json()["deleted_at"] is None
    assert get_items(client)["total"] == 1 and get_items(client)["items"][0]["id"] == second_id
    assert all(row.deleted_at is None for row in _rows())


def test_a_task_in_the_bin_accepts_no_other_action(client):
    run_id = _seed(client, name="x", status="failed", quality="draft")
    assert _delete(client, run_id).status_code == 204
    base = f"/api/v1/translation-runs/{run_id}"
    assert client.patch(base, headers=OWNER, json={"display_name": "y"}).status_code == 404
    assert client.post(f"{base}/restore", headers=OWNER).status_code == 404
    assert client.post(f"{base}/cancel", headers=OWNER).status_code == 404
    assert client.get(f"{base}/versions", headers=OWNER).status_code == 404
    assert client.post(f"{base}/revisions", headers=OWNER, json={}).status_code == 404


def test_restoring_is_for_the_submitter_or_an_admin_and_is_idempotent(client):
    run_id = _seed(client, status="failed", quality="draft")
    assert _delete(client, run_id).status_code == 204
    url = f"/api/v1/translation-runs/{run_id}/restore-from-trash"
    assert client.post(url, headers=REVIEWER).status_code == 403
    assert client.post(url, headers=OTHER_TENANT).status_code == 404
    assert client.post(url, headers=OWNER).status_code == 200
    assert client.post(url, headers=OWNER).status_code == 200  # already restored: same answer
    assert get_items(client)["total"] == 1


def test_reviewers_cannot_delete_but_the_bin_is_tenant_scoped(client):
    run_id = _seed(client, status="failed", quality="draft")
    assert _delete(client, run_id, REVIEWER).status_code == 403
    assert _delete(client, run_id, OTHER).status_code == 404
    assert _delete(client, run_id, ADMIN).status_code == 204
    assert client.get("/api/v1/translation-runs", headers=OTHER_TENANT, params={"trash": "true"}).json()["total"] == 0
    assert client.get("/api/v1/translation-runs", headers=OTHER, params={"trash": "true"}).json()["total"] == 0  # not theirs


def test_the_source_stays_referenced_so_a_deleted_task_keeps_its_precheck(client):
    run_id = _seed(client, status="failed", quality="draft")
    with persist_db.SessionLocal() as session:
        preflight_id = session.get(TranslationRunRecord, run_id).preflight_id
    assert _delete(client, run_id).status_code == 204
    assert client.delete(f"/api/v1/preflights/{preflight_id}", headers=OWNER).status_code == 409


# --- permanent purge ---------------------------------------------------------------------------------------------


def _purge(client, run_id, headers=ADMIN):
    return client.post(f"/api/v1/translation-runs/{run_id}/purge", headers=headers)


def test_purge_is_admin_only_and_only_for_tasks_in_the_bin(client):
    run_id = _seed(client, status="failed", quality="draft")
    assert _purge(client, run_id).status_code == 409  # not in the bin
    assert _delete(client, run_id).status_code == 204
    assert _purge(client, run_id, OWNER).status_code == 403
    assert _purge(client, run_id, REVIEWER).status_code == 403
    assert _purge(client, run_id, OTHER_TENANT).status_code == 404


def test_purge_removes_rows_and_files_and_keeps_a_tombstone_with_the_review_decisions(client, tmp_path):
    run_id = _seed(client, name="方案", filename="secret-protocol.pdf", status="failed", quality="draft")
    files = _with_files(client, tmp_path, run_id)
    assert _delete(client, run_id).status_code == 204
    done = _purge(client, run_id)
    assert done.status_code == 200 and done.json()["purged"] is True
    assert not any(path.exists() for path in files.values())
    assert _rows() == []
    with persist_db.SessionLocal() as session:
        assert session.scalar(select(PreflightRecord.id).where(PreflightRecord.source_filename == "secret-protocol.pdf")) is None
        tomb = session.scalars(select(AuditEvent).where(AuditEvent.action == "translation_run.purge")).one()
        extra = tomb.extra
        assert extra["review_decisions"][0]["decision"] == "request_changes"
        assert extra["review_decisions"][0]["comment"] == "数字不一致"
        assert "secret-protocol" not in str(extra)  # the file name is kept as a digest only
        assert extra["source_filename_digest"]
        assert session.scalars(select(AuditEvent).where(AuditEvent.action == "translation_run.purged")).one()


def test_a_failed_file_removal_keeps_the_rows_marks_the_task_and_can_be_retried(client, tmp_path, monkeypatch):
    run_id = _seed(client, status="failed", quality="draft")
    files = _with_files(client, tmp_path, run_id)
    assert _delete(client, run_id).status_code == 204
    real = api_v1._remove_purged_files
    monkeypatch.setattr(api_v1, "_remove_purged_files", lambda f, d: ["out.docx: locked"])
    failed = _purge(client, run_id)
    assert failed.status_code == 200 and failed.json()["purged"] is False
    row = _rows(run_id)[0]
    assert row.purge_status == "failed" and "locked" in row.purge_error
    assert files["source"].exists()  # nothing was deleted by the fake
    listed = _trash(client)["items"][0]
    assert listed["purge_status"] == "failed" and "restore_from_trash" not in listed["allowed_actions"]
    restore = client.post(f"/api/v1/translation-runs/{run_id}/restore-from-trash", headers=OWNER)
    assert restore.status_code == 409 and restore.json()["detail"]["code"] == "PURGE_FAILED"
    monkeypatch.setattr(api_v1, "_remove_purged_files", real)
    assert _purge(client, run_id).json()["purged"] is True
    assert _rows() == [] and not files["source"].exists()


def test_a_crash_after_the_decision_is_committed_leaves_a_hidden_task_that_a_retry_finishes(client, tmp_path, monkeypatch):
    run_id = _seed(client, status="failed", quality="draft")
    files = _with_files(client, tmp_path, run_id)
    assert _delete(client, run_id).status_code == 204

    def crash(*args, **kwargs):
        raise RuntimeError("process died")

    real = api_v1._complete_purge
    monkeypatch.setattr(api_v1, "_complete_purge", crash)
    assert _purge(client, run_id).json()["purged"] is False
    row = _rows(run_id)[0]
    assert row.purge_status == "pending"  # the row is still there, so the files are still accounted for
    assert all(path.exists() for path in files.values())
    assert get_items(client)["total"] == 0  # and it is invisible meanwhile
    assert client.post(f"/api/v1/translation-runs/{run_id}/restore-from-trash", headers=OWNER).status_code == 409
    monkeypatch.setattr(api_v1, "_complete_purge", real)
    assert _purge(client, run_id).json()["purged"] is True
    assert _rows() == [] and not any(path.exists() for path in files.values())


def test_a_crash_before_the_decision_is_committed_changes_nothing(client, tmp_path, monkeypatch):
    run_id = _seed(client, status="failed", quality="draft")
    files = _with_files(client, tmp_path, run_id)
    assert _delete(client, run_id).status_code == 204

    def crash(*args, **kwargs):
        raise RuntimeError("database went away")

    real = api_v1._begin_purge
    monkeypatch.setattr(api_v1, "_begin_purge", crash)
    with pytest.raises(RuntimeError):
        _purge(client, run_id)
    monkeypatch.setattr(api_v1, "_begin_purge", real)
    assert _rows(run_id)[0].purge_status is None
    assert all(path.exists() for path in files.values())


def test_a_source_file_shared_with_another_precheck_is_not_removed(client, tmp_path):
    run_id = _seed(client, status="failed", quality="draft")
    files = _with_files(client, tmp_path, run_id)
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        mine = session.get(PreflightRecord, run.preflight_id)
        session.add(
            PreflightRecord(
                tenant_id=mine.tenant_id, actor_sub="owner1", source_filename="other.pdf", source_format="pdf",
                source_sha256="e" * 64, size_bytes=1, storage_key=mine.storage_key,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        session.commit()
    assert _delete(client, run_id).status_code == 204
    assert _purge(client, run_id).json()["purged"] is True
    assert files["source"].exists()  # someone else still points at it
    assert not files["artifact"].exists() and not files["work"].exists()


def test_a_purge_never_deletes_outside_the_runner_root(client, tmp_path):
    outside = tmp_path / "keep-me"
    outside.mkdir()
    (outside / "file.txt").write_text("x")
    dirs = api_v1._run_work_dirs([type("R", (), {"tenant_id": "..", "id": "..", "generation": 1})()])
    assert dirs == []  # ../.. resolves above the root and is dropped
    assert (outside / "file.txt").exists()


def test_expired_bins_are_reported_and_only_purged_when_asked(client, tmp_path):
    old = _seed(client, name="old", status="failed", quality="draft")
    fresh = _seed(client, name="fresh", status="failed", quality="draft")
    old_files = _with_files(client, tmp_path, old)
    assert _delete(client, old).status_code == 204 and _delete(client, fresh).status_code == 204
    with persist_db.SessionLocal() as session:
        row = session.get(TranslationRunRecord, old)
        row.purge_after = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()
        report = api_v1.purge_expired_runs(session, execute=False)
        assert report["due"] == 1 and report["items"][0]["run_id"] == old and report["purged"] == 0
        assert session.get(TranslationRunRecord, old) is not None and old_files["source"].exists()
        done = api_v1.purge_expired_runs(session, execute=True)
        assert done["purged"] == 1 and done["failed"] == 0
        assert session.get(TranslationRunRecord, old) is None
        assert session.get(TranslationRunRecord, fresh) is not None  # not due yet
    assert not old_files["source"].exists()

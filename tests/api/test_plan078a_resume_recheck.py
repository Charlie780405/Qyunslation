"""PLAN-078a: resuming an interrupted run must not keep the verdict for the output it replaces."""
from __future__ import annotations

from sqlalchemy import select

from _plan078_flow import ADMIN, make_client, run_to_gate
from qyunslation.api import v1 as api_v1_module
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import reset_engine
from qyunslation.persist.models import QaItem, TranslationRunRecord


def test_resume_clears_the_old_verdict_so_new_output_is_rechecked(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "resume-recheck")
        assert state["quality_state"] == "qa_blocked"
        with persist_db.SessionLocal() as session:
            run = session.get(TranslationRunRecord, run_id)
            run.status = "interrupted"  # e.g. the heartbeat gave up on it
            session.commit()

        async def stub_launch(*, run, preflight, target_language, **kwargs):
            run.status = "translating"
            run.stage = "text"

        monkeypatch.setattr(api_v1_module, "_launch_translation_run", stub_launch)
        resumed = client.post(f"/api/v1/translation-runs/{run_id}/resume", headers=ADMIN)
        assert resumed.status_code == 200, resumed.text
        body = resumed.json()
        assert body["status"] == "translating"
        assert body["quality_state"] == "draft"
        assert body["qa_summary"].get("blocker", 0) == 0
        with persist_db.SessionLocal() as session:
            # PLAN-078b: the old verdict is kept as history but no longer counts as current.
            rows = session.scalars(select(QaItem).where(QaItem.run_id == run_id)).all()
            assert rows and not any(row.is_current for row in rows)
    reset_engine()

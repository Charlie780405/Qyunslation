"""PLAN-078e rollback helper: bin -> archive, dry-run by default, never touching a half-purged task."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qyunslation.persist.models import Base, PreflightRecord, Tenant, TranslationRunRecord

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan078e-trash-to-archive.py"


def _seed(url: str) -> tuple[str, str, str]:
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        tenant = Tenant(slug="pilot", name="pilot")
        session.add(tenant)
        session.flush()
        ids = []
        for index, purge in enumerate((None, "failed", None)):
            preflight = PreflightRecord(
                tenant_id=tenant.id, actor_sub="u", source_filename=f"f{index}.pdf", source_format="pdf",
                source_sha256=f"{index:064x}", size_bytes=1, storage_key=f"{tenant.id}/{index}", expires_at=now,
            )
            session.add(preflight)
            session.flush()
            run = TranslationRunRecord(
                preflight_id=preflight.id, tenant_id=tenant.id, actor_sub="u", idempotency_key_hash=f"{index:064x}",
                direction="English → 简体中文", profile="p", status="failed",
                deleted_at=now if index < 2 else None, deleted_by="u" if index < 2 else None,
                purge_after=now if index < 2 else None, purge_status=purge,
            )
            session.add(run)
            session.flush()
            ids.append(run.id)
        session.commit()
    return tuple(ids)  # type: ignore[return-value]


def _run(url: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env={"QYUNSLATION_DATABASE_URL": url, "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=120,
    )


def _state(url: str, run_id: str) -> tuple:
    with Session(create_engine(url)) as session:
        run = session.get(TranslationRunRecord, run_id)
        return run.deleted_at is not None, run.archived_at is not None


def test_dry_run_changes_nothing_and_apply_archives_only_whole_bin_tasks(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}"
    in_bin, half_purged, active = _seed(url)
    dry = _run(url)
    assert dry.returncode == 0 and "dry-run: 1 task(s)" in dry.stdout and "1 skipped" in dry.stdout
    assert _state(url, in_bin) == (True, False)
    applied = _run(url, "--apply")
    assert applied.returncode == 0 and "changed 1 task(s)" in applied.stdout
    assert _state(url, in_bin) == (False, True)  # archived, no longer in the bin
    assert _state(url, half_purged) == (True, False)  # left alone: its files may already be gone
    assert _state(url, active) == (False, False)

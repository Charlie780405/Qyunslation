# SPDX-License-Identifier: MPL-2.0
"""PLAN-071 迁移：真实 Alembic 升级/降级/回填（SQLite）。"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[2]
pytest.importorskip("alembic")


def _alembic(db_url: str, *args: str) -> None:
    env = {**os.environ, "QYUNSLATION_DATABASE_URL": db_url}
    proc = subprocess.run(
        [sys.executable, "-c", "from alembic.config import main; main()", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=170,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _tables(engine):
    return set(sa.inspect(engine).get_table_names())


def _insert(conn, table, **overrides):
    meta = sa.MetaData()
    tbl = sa.Table(table, meta, autoload_with=conn)
    values = {}
    for col in tbl.columns:
        if col.name in overrides:
            continue
        if col.nullable or col.server_default is not None:
            continue
        kind = type(col.type).__name__.upper()
        if "INT" in kind:
            values[col.name] = 1
        elif "BOOL" in kind:
            values[col.name] = False
        elif "DATE" in kind:
            from datetime import datetime, timezone

            values[col.name] = datetime.now(timezone.utc)
        elif "JSON" in kind:
            values[col.name] = {}
        else:
            values[col.name] = str(uuid.uuid4())[: getattr(col.type, "length", None) or 36]
    values.update(overrides)
    conn.execute(tbl.insert().values(**values))


def test_upgrade_downgrade_roundtrip(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'mig.db'}"
    _alembic(url, "upgrade", "head")
    engine = sa.create_engine(url)
    assert {"translation_stage_event", "qa_item", "review_decision", "model_profile_version"} <= _tables(engine)
    cols = {c["name"] for c in sa.inspect(engine).get_columns("translation_run_record")}
    assert {"quality_state", "document_classification", "model_profile_id"} <= cols

    _alembic(url, "downgrade", "068f0001")
    engine = sa.create_engine(url)
    assert "translation_stage_event" not in _tables(engine)
    cols = {c["name"] for c in sa.inspect(engine).get_columns("translation_run_record")}
    assert "quality_state" not in cols

    _alembic(url, "upgrade", "head")
    assert "translation_stage_event" in _tables(sa.create_engine(url))


def test_legacy_backfill_marks_succeeded_runs_and_artifacts(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}"
    _alembic(url, "upgrade", "068f0001")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        _insert(conn, "translation_run_record", id="done-1", status="succeeded", stage="export")
        _insert(conn, "translation_run_record", id="live-1", status="translating", stage="text")
        _insert(
            conn,
            "translation_artifact",
            id="art-1",
            run_id="done-1",
            kind="formal",
            artifact_key="formal:pdf",
            formal_export=True,
        )
    _alembic(url, "upgrade", "head")
    with engine.connect() as conn:
        states = dict(conn.execute(sa.text("select id, quality_state from translation_run_record")).all())
        kinds = dict(conn.execute(sa.text("select id, kind from translation_artifact")).all())
    assert states["done-1"] == "legacy_unverified"
    assert states["live-1"] == "draft"
    assert kinds["art-1"] == "legacy"

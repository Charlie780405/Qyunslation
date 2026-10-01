# SPDX-License-Identifier: MPL-2.0
"""PLAN-072 迁移：upload_session / review_draft / heartbeat 列。"""
from __future__ import annotations

import os
import subprocess
import sys
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


def test_plan072_tables_and_columns(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / '072.db'}"
    _alembic(url, "upgrade", "head")
    engine = sa.create_engine(url)
    tables = set(sa.inspect(engine).get_table_names())
    assert {"upload_session", "review_draft"} <= tables
    cols = {c["name"] for c in sa.inspect(engine).get_columns("translation_run_record")}
    assert {"heartbeat_at", "lease_owner"} <= cols
    _alembic(url, "downgrade", "071g0002")
    tables = set(sa.inspect(engine).get_table_names())
    assert "upload_session" not in tables
    assert "review_draft" not in tables

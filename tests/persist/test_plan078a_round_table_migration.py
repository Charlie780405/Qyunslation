"""PLAN-078a: 078a0002 creates qa_check_round, enforces one live round per run generation, and rolls back."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "078a0002_qa_check_round.py"


def _load():
    spec = importlib.util.spec_from_file_location("m078a0002", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def conn():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE translation_run_record (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(sa.text("INSERT INTO translation_run_record VALUES ('run-1')"))
        yield connection


def _insert(conn, round_id, round_no, status):
    conn.execute(
        sa.text(
            "INSERT INTO qa_check_round (id, run_id, generation, round_no, trigger, status, created_at) "
            "VALUES (:i, 'run-1', 1, :n, 'auto', :s, '2026-10-19')"
        ),
        {"i": round_id, "n": round_no, "s": status},
    )


def test_upgrade_creates_table_and_single_live_round_index(conn):
    with Operations.context(MigrationContext.configure(conn)):
        _load().upgrade()
    _insert(conn, "r1", 1, "pending")
    with pytest.raises(sa.exc.IntegrityError):
        with conn.begin_nested():
            _insert(conn, "r2", 2, "running")  # a second live round for the same run generation
    _insert(conn, "r3", 3, "succeeded")  # history is unlimited
    _insert(conn, "r4", 4, "failed")
    with pytest.raises(sa.exc.IntegrityError):
        with conn.begin_nested():
            _insert(conn, "r5", 4, "succeeded")  # round numbers never repeat


def test_a_finished_round_frees_the_slot(conn):
    with Operations.context(MigrationContext.configure(conn)):
        _load().upgrade()
    _insert(conn, "r1", 1, "running")
    conn.execute(sa.text("UPDATE qa_check_round SET status = 'succeeded' WHERE id = 'r1'"))
    _insert(conn, "r2", 2, "pending")  # a re-check can now be registered


def test_downgrade_removes_the_table(conn):
    module = _load()
    with Operations.context(MigrationContext.configure(conn)):
        module.upgrade()
        module.downgrade()
    tables = sa.inspect(conn).get_table_names()
    assert "qa_check_round" not in tables

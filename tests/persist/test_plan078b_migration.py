"""PLAN-078b: 078b0001 is additive, keeps existing rows current, and downgrades cleanly."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "078b0001_qa_resolution.py"


def _load():
    spec = importlib.util.spec_from_file_location("m078b0001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def conn():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE translation_run_record (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(
            sa.text(
                "CREATE TABLE qa_item (id VARCHAR(36) PRIMARY KEY, run_id VARCHAR(36), generation INTEGER, "
                "severity VARCHAR(16), code VARCHAR(64))"
            )
        )
        connection.execute(sa.text("CREATE TABLE qa_check_round (id VARCHAR(36) PRIMARY KEY, run_id VARCHAR(36))"))
        connection.execute(sa.text("INSERT INTO translation_run_record VALUES ('run-1')"))
        connection.execute(sa.text("INSERT INTO qa_item VALUES ('i1', 'run-1', 1, 'blocker', 'LOGO_MISSING')"))
        yield connection


def test_existing_items_stay_current_and_gain_nullable_identity(conn):
    with Operations.context(MigrationContext.configure(conn)):
        _load().upgrade()
    row = conn.execute(sa.text("SELECT is_current, fingerprint, rule_class, round_id, location_json FROM qa_item")).one()
    assert row[0] in (1, True)  # old verdicts remain the current verdict
    assert row[1:] == (None, None, None, None)
    columns = {c["name"] for c in sa.inspect(conn).get_columns("qa_check_round")}
    assert {"rule_set_version", "artifact_digest", "diff_json"} <= columns


def test_disposition_table_is_created(conn):
    with Operations.context(MigrationContext.configure(conn)):
        _load().upgrade()
    inspector = sa.inspect(conn)
    assert "qa_disposition" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("qa_disposition")}
    assert {"fingerprint", "action", "reason", "actor_sub", "actor_role", "self_review", "artifact_digest"} <= columns
    conn.execute(
        sa.text(
            "INSERT INTO qa_disposition (id, run_id, generation, fingerprint, code, rule_class, action, reason, "
            "actor_sub, actor_role, created_at) VALUES ('d1','run-1',1,'f','LOGO_MISSING','C2','grant_waiver',"
            "'reason text','u','reviewer','2026-10-19')"
        )
    )
    assert conn.scalar(sa.text("SELECT self_review FROM qa_disposition")) in (0, False)


def test_downgrade_restores_the_previous_shape(conn):
    module = _load()
    with Operations.context(MigrationContext.configure(conn)):
        module.upgrade()
        module.downgrade()
    inspector = sa.inspect(conn)
    assert "qa_disposition" not in inspector.get_table_names()
    assert "fingerprint" not in {c["name"] for c in inspector.get_columns("qa_item")}
    assert conn.scalar(sa.text("SELECT count(*) FROM qa_item")) == 1  # data intact


def test_chain_extends_078a():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = MIGRATION.parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1
    assert script.get_revision("078b0001").down_revision == "078a0002"

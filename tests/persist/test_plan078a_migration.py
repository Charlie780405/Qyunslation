"""PLAN-078a: the gated backfill relabels only runs that wait at the gate, and downgrades cleanly."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "078a0001_gated_status_backfill.py"


def _load():
    spec = importlib.util.spec_from_file_location("m078a0001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def conn():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE translation_run_record (id TEXT PRIMARY KEY, status TEXT, quality_state TEXT)")
        )
        connection.execute(sa.text("CREATE TABLE qa_item (id TEXT PRIMARY KEY, severity TEXT)"))
        rows = [
            ("blocked-at-gate", "translating", "qa_blocked"),
            ("review-at-gate", "translating", "review_ready"),
            ("degraded-at-gate", "translating", "qa_degraded"),
            ("really-running", "translating", "draft"),
            ("queued", "queued", "draft"),
            ("heartbeat-interrupted", "interrupted", "qa_blocked"),
            ("done", "succeeded", "approved"),
        ]
        for run_id, status, quality in rows:
            connection.execute(
                sa.text("INSERT INTO translation_run_record VALUES (:i, :s, :q)"),
                {"i": run_id, "s": status, "q": quality},
            )
        connection.execute(sa.text("INSERT INTO qa_item VALUES ('a', 'unavailable'), ('b', 'blocker')"))
        yield connection


def _statuses(conn):
    return dict(conn.execute(sa.text("SELECT id, status FROM translation_run_record")).all())


def test_upgrade_relabels_only_runs_waiting_at_the_gate(conn):
    module = _load()
    with Operations.context(MigrationContext.configure(conn)):
        module.upgrade()
    got = _statuses(conn)
    assert got["blocked-at-gate"] == got["review-at-gate"] == got["degraded-at-gate"] == "gated"
    assert got["really-running"] == "translating"  # no verdict yet: genuinely executing
    assert got["queued"] == "queued"
    assert got["heartbeat-interrupted"] == "interrupted"  # left for the operator to decide
    assert got["done"] == "succeeded"


def test_downgrade_restores_values_the_old_release_understands(conn):
    module = _load()
    conn.execute(sa.text("UPDATE translation_run_record SET status='gated' WHERE id='blocked-at-gate'"))
    conn.execute(
        sa.text("UPDATE translation_run_record SET status='gated', quality_state='qa_unavailable' WHERE id='review-at-gate'")
    )
    conn.execute(
        sa.text("UPDATE translation_run_record SET status='gated', quality_state='changes_requested' WHERE id='degraded-at-gate'")
    )
    with Operations.context(MigrationContext.configure(conn)):
        module.downgrade()
    rows = {
        row[0]: (row[1], row[2])
        for row in conn.execute(sa.text("SELECT id, status, quality_state FROM translation_run_record"))
    }
    assert rows["blocked-at-gate"] == ("translating", "qa_blocked")
    assert rows["review-at-gate"] == ("translating", "qa_blocked")
    assert rows["degraded-at-gate"] == ("translating", "draft")
    severities = {r[0]: r[1] for r in conn.execute(sa.text("SELECT id, severity FROM qa_item"))}
    assert severities == {"a": "blocker", "b": "blocker"}


def test_migrations_form_a_single_chain_on_top_of_074():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = MIGRATION.parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1  # no accidental branch
    chain = [rev.revision for rev in script.walk_revisions()]  # newest first
    assert chain.index("078a0002") < chain.index("078a0001") < chain.index("074a0001")
    assert script.get_revision("078a0001").down_revision == "074a0001"
    assert script.get_revision("078a0002").down_revision == "078a0001"

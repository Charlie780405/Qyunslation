# SPDX-License-Identifier: MPL-2.0
"""PLAN-060 migration must remain portable for local regression runs."""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_plan060_workbench_run_migration_upgrades_and_downgrades_on_sqlite(tmp_path, monkeypatch):
    database = tmp_path / "plan060.sqlite"
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", f"sqlite:///{database}")
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    inspector = inspect(create_engine(f"sqlite:///{database}"))
    assert "workbench_translation_run" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("workbench_translation_run")}
    assert {"job_id", "tenant_id", "actor_sub", "term_policy", "degradation_reason"} <= columns

    command.downgrade(config, "058b0001")
    downgraded = inspect(create_engine(f"sqlite:///{database}"))
    assert "workbench_translation_run" not in downgraded.get_table_names()

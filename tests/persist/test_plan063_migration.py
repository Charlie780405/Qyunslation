# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_plan063_excluded_stats_migration_upgrades_and_downgrades(tmp_path, monkeypatch):
    database = tmp_path / "plan063.sqlite"
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", f"sqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    inspector = inspect(create_engine(f"sqlite:///{database}"))
    columns = {column["name"] for column in inspector.get_columns("workbench_translation_run")}
    assert "excluded_stats" in columns
    command.downgrade(config, "060a0001")
    downgraded = inspect(create_engine(f"sqlite:///{database}"))
    gone = {column["name"] for column in downgraded.get_columns("workbench_translation_run")}
    assert "excluded_stats" not in gone

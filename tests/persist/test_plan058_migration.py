# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：从空 SQLite 数据库验证完整 Alembic 链路可执行。"""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_plan058_migration_is_portable_to_sqlite(tmp_path, monkeypatch):
    database = tmp_path / "plan058.sqlite"
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", f"sqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "head")

    inspector = inspect(create_engine(f"sqlite:///{database}"))
    tables = set(inspector.get_table_names())
    assert {
        "concept_term_embedding",
        "document_term_candidate",
        "document_term_occurrence",
        "term_decision",
    } <= tables
    assert "project_id" in {column["name"] for column in inspector.get_columns("concept")}
    assert "normalized_text" in {
        column["name"] for column in inspector.get_columns("concept_term")
    }

    command.downgrade(config, "055a0001")
    downgraded = inspect(create_engine(f"sqlite:///{database}"))
    assert "concept_term_embedding" not in downgraded.get_table_names()
    assert "document_term_candidate" not in downgraded.get_table_names()
    assert "project_id" not in {
        column["name"] for column in downgraded.get_columns("concept")
    }

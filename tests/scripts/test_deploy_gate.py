# SPDX-License-Identifier: MPL-2.0
"""PLAN-075b：部署门禁脚本契约测试。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import deploy_gate as dg  # noqa: E402


def test_plan074_probe_routes_defined():
    assert len(dg.PLAN074_PROBE_ROUTES) >= 2
    methods = {m for m, _ in dg.PLAN074_PROBE_ROUTES}
    assert "GET" in methods
    assert "POST" in methods


def test_check_api_routes_accepts_auth_errors():
    def fake_probe(_base, method, path):
        if method == "GET":
            return 401
        return 405

    with patch.object(dg, "probe_http", side_effect=fake_probe):
        ok, msg, rows = dg.check_api_routes("http://127.0.0.1:8010")
    assert ok is True
    assert rows[0]["status"] == 401


def test_check_api_routes_rejects_404():
    with patch.object(dg, "probe_http", return_value=404):
        ok, msg, rows = dg.check_api_routes("http://127.0.0.1:8010")
    assert ok is False
    assert "404" in msg or "stale" in msg


def test_check_frontend_fresh_detects_stale_src(tmp_path: Path):
    root = tmp_path / "repo"
    src = root / "frontend" / "src" / "next"
    static = root / "qyunslation" / "static" / "app"
    src.mkdir(parents=True)
    static.mkdir(parents=True)
    page = src / "Page.vue"
    page.write_text("<template></template>", encoding="utf-8")
    index = static / "index.html"
    index.write_text("<html></html>", encoding="utf-8")
    # Make source newer than index
    import os
    import time

    old = time.time() - 3600
    os.utime(index, (old, old))
    ok, msg, _ = dg.check_frontend_fresh(root)
    assert ok is False
    assert "newer" in msg


def test_check_migration_aligned(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    with patch.object(dg, "alembic_heads", return_value=["074a0001"]):
        with patch.object(dg, "alembic_current", return_value="074a0001"):
            ok, msg, detail = dg.check_migration_aligned()
    assert ok is True
    assert detail["current"] == "074a0001"


def test_check_migration_mismatch(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    with patch.object(dg, "alembic_heads", return_value=["074a0001"]):
        with patch.object(dg, "alembic_current", return_value="073a0001"):
            ok, msg, _ = dg.check_migration_aligned()
    assert ok is False
    assert "073a0001" in msg

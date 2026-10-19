# SPDX-License-Identifier: MPL-2.0
"""PLAN-079 F12: a reused pre-check re-evaluates the language hint for the language chosen now."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base

OWNER = {"X-Dev-User": "owner1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"}
CHINESE = ("申办者应当确保临床研究按照方案开展，受试者每天服用一次研究药物，持续十二周，并在每次访视时接受评估。" * 6).encode()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_PREFLIGHT_PROBE", "1")
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_PREFLIGHT_ROOT", str(tmp_path / "preflights"))
    monkeypatch.setenv("QYUNSLATION_UPLOAD_ROOT", str(tmp_path / "uploads"))
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _upload(client, source, target):
    return client.post(
        "/api/v1/preflights", headers=OWNER,
        data={"source_language": source, "target_language": target},
        files={"file": ("zh.txt", CHINESE, "text/plain")},
    ).json()


def _mismatch(body):
    return [item for item in body["issues"] if item["code"] == "LANGUAGE_MISMATCH"]


def test_choosing_the_right_language_on_reuse_clears_the_old_warning(client):
    first = _upload(client, "English", "简体中文")
    assert len(_mismatch(first)) == 1  # Chinese text, English chosen
    second = _upload(client, "简体中文", "English")
    assert second["reused"] is True and second["id"] == first["id"]
    assert _mismatch(second) == []
    assert second["source_language"] == "简体中文"


def test_choosing_the_wrong_language_on_reuse_brings_the_warning_back(client):
    first = _upload(client, "简体中文", "English")
    assert _mismatch(first) == []
    second = _upload(client, "English", "简体中文")
    assert second["reused"] is True
    assert len(_mismatch(second)) == 1


def test_same_language_on_reuse_leaves_the_issues_alone(client):
    first = _upload(client, "English", "简体中文")
    again = _upload(client, "English", "简体中文")
    assert again["reused"] is True and again["issues"] == first["issues"]


def test_other_issues_survive_the_language_refresh(client):
    first = _upload(client, "English", "简体中文")
    first_codes = {item["code"] for item in first["issues"]} - {"LANGUAGE_MISMATCH"}
    second = _upload(client, "简体中文", "English")
    assert {item["code"] for item in second["issues"]} == first_codes

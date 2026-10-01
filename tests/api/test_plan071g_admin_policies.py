# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base


@pytest.fixture()
def client(monkeypatch):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


ADMIN = {"X-Dev-User": "root", "X-Dev-Tenant": "pilot", "X-Dev-Role": "system_admin"}
USER = {"X-Dev-User": "alice", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"}


def _lock_reduce_motion(client):
    return client.put(
        "/api/v1/admin/policies",
        headers=ADMIN,
        json={"policies": {"reduceMotion": {"value": True, "locked": True, "reason": "无障碍合规要求"}}},
    )


def test_non_admin_cannot_read_or_write_policies(client):
    assert client.get("/api/v1/admin/policies", headers=USER).status_code == 403
    assert client.put("/api/v1/admin/policies", headers=USER, json={"policies": {}}).status_code == 403


def test_admin_policy_is_persisted_and_audited_in_payload(client):
    resp = _lock_reduce_motion(client)
    assert resp.status_code == 200, resp.text
    again = client.get("/api/v1/admin/policies", headers=ADMIN).json()
    assert again["policies"]["reduceMotion"] == {
        "value": True,
        "locked": True,
        "reason": "无障碍合规要求",
        "updated_by": "root",
    }


def test_effective_reports_system_source_and_lock_reason(client):
    _lock_reduce_motion(client)
    eff = client.get("/api/v1/settings/effective", headers=USER).json()["effective"]
    assert eff["reduceMotion"] == {
        "value": True,
        "source": "system",
        "locked": True,
        "lock_reason": "无障碍合规要求",
    }
    assert eff["density"]["source"] == "default"


def test_locked_field_put_is_rejected_with_reason(client):
    _lock_reduce_motion(client)
    denied = client.put("/api/v1/preferences", headers=USER, json={"preferences": {"reduceMotion": False}})
    assert denied.status_code == 403
    detail = denied.json()["detail"]
    assert detail["code"] == "PREFERENCE_LOCKED" and detail["key"] == "reduceMotion"
    assert "无障碍" in detail["reason"]


def test_locked_field_resubmitted_with_policy_value_is_accepted(client):
    _lock_reduce_motion(client)
    ok = client.put(
        "/api/v1/preferences", headers=USER, json={"preferences": {"reduceMotion": True, "density": "compact"}}
    )
    assert ok.status_code == 200
    got = client.get("/api/v1/preferences", headers=USER).json()
    assert got["preferences"]["reduceMotion"] is True
    assert got["preferences"]["density"] == "compact"
    assert got["locked"] == ["reduceMotion"]


def test_unlocked_system_default_is_overridable_by_user(client):
    client.put(
        "/api/v1/admin/policies",
        headers=ADMIN,
        json={"policies": {"density": {"value": "compact", "locked": False}}},
    )
    eff = client.get("/api/v1/settings/effective", headers=USER).json()["effective"]
    assert eff["density"]["value"] == "compact" and eff["density"]["source"] == "system"
    client.put("/api/v1/preferences", headers=USER, json={"preferences": {"density": "comfortable"}})
    eff = client.get("/api/v1/settings/effective", headers=USER).json()["effective"]
    assert eff["density"]["value"] == "comfortable" and eff["density"]["source"] == "user"


def test_invalid_policy_requests_are_rejected(client):
    bad_key = client.put("/api/v1/admin/policies", headers=ADMIN, json={"policies": {"nope": {"value": 1}}})
    assert bad_key.status_code == 400
    no_reason = client.put(
        "/api/v1/admin/policies", headers=ADMIN, json={"policies": {"largeText": {"value": True, "locked": True}}}
    )
    assert no_reason.status_code == 400
    bad_value = client.put(
        "/api/v1/admin/policies", headers=ADMIN, json={"policies": {"density": {"value": "huge"}}}
    )
    assert bad_value.status_code == 400
    removed = client.put("/api/v1/admin/policies", headers=ADMIN, json={"policies": {"density": None}})
    assert removed.status_code == 200

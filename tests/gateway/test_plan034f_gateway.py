# SPDX-License-Identifier: MPL-2.0
"""PLAN-034f：网关档位 / provenance / 风险 / QA / repair。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.gateway.config import (
    BASELINE_MODEL_ID,
    ProfileNotWiredError,
    apply_gateway_profile,
    build_provenance,
    resolve_profile,
)
from qyunslation.gateway.pipeline import run_segment_pipeline
from qyunslation.gateway.qa import CHECKLIST, ensure_checklist_coverage, run_deterministic_qa
from qyunslation.gateway.risk import grade_risk
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base


def test_quality_profile_baseline():
    resolved = resolve_profile("quality")
    assert resolved["model_id"] == BASELINE_MODEL_ID
    assert resolved["wired"] is True
    assert resolved["provider"] == "qwen_ollama"


def test_unwired_profiles_raise():
    with pytest.raises(ProfileNotWiredError):
        resolve_profile("fast")
    with pytest.raises(ProfileNotWiredError):
        resolve_profile("fallback")
    with pytest.raises(ProfileNotWiredError):
        resolve_profile("nope")


def test_apply_gateway_does_not_override_user():
    class P:
        model_id = "user-model"
        base_url = "http://example.invalid/v1"

    p = P()
    apply_gateway_profile(p, profile="quality")
    assert p.model_id == "user-model"
    assert p.base_url == "http://example.invalid/v1"

    class Empty:
        model_id = None
        base_url = None

    e = Empty()
    apply_gateway_profile(e, profile="quality")
    assert e.model_id == BASELINE_MODEL_ID


def test_build_provenance_strips_secrets(monkeypatch):
    monkeypatch.setenv(
        "QYUNSLATION_BASE_URL", "https://user:pass@ollama.example:11434/v1?api_key=x"
    )
    prov = build_provenance(extra={"api_key": "sk-secret", "note": "ok"})
    assert "api_key" not in prov
    assert "sk-secret" not in str(prov)
    assert "pass" not in (prov.get("endpoint") or "")
    assert "?" not in (prov.get("endpoint") or "")
    assert prov["model_id"] == BASELINE_MODEL_ID
    assert prov["profile"] == "quality"
    assert prov["tm_version"]
    assert prov["glossary_version"]


def test_references_preserve():
    risk = grade_risk("literature", "references")
    assert risk["policy"] == "PRESERVE"
    qa = run_deterministic_qa(
        "Smith J. Nature 2020.",
        "史密斯。自然 2020。",
        role="references",
    )
    assert qa.blocked is True
    assert any(f.check == "references" for f in qa.findings)


def test_missing_number_is_critical():
    qa = run_deterministic_qa(
        "Dose was 10 mg at week 12",
        "剂量为毫克，在第周",
        role="table",
        domain="csr",
    )
    assert qa.blocked is True
    assert any(
        f.check in {"numbers", "doses"} and f.severity == "critical" for f in qa.findings
    )


def test_negation_loss_is_critical():
    qa = run_deterministic_qa(
        "The patient did not receive placebo",
        "受试者接受了安慰剂",
        role="body",
    )
    assert any(f.check == "negation" for f in qa.findings)
    assert qa.blocked is True


def test_checklist_twelve_items():
    assert len(CHECKLIST) == 12
    assert ensure_checklist_coverage() == list(CHECKLIST)


def test_mock_repair_then_pass():
    class MockProv:
        def translate(self, source, *, system=None):
            return "坏译文"

        def review(self, source, target, *, findings=None):
            return "issues"

        def repair(self, source, target, *, findings=None):
            return "剂量为 10 mg，在第 12 周"

    out = run_segment_pipeline(
        "Dose was 10 mg at week 12",
        target="剂量丢失",
        role="body",
        provider=MockProv(),
        enable_repair=True,
    )
    assert out["repaired"] is True
    assert out["repaired_text"]
    assert "10" in (out["target"] or "")
    assert "12" in (out["target"] or "")


@pytest.fixture()
def client(monkeypatch):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_BASE_URL", "http://127.0.0.1:11434/v1")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as c:
        yield c
    reset_engine()


def test_api_provenance_strips_key(client):
    headers = {"X-Dev-User": "u", "X-Dev-Tenant": "gw"}
    proj = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"slug": "p1", "name": "P1"},
    )
    assert proj.status_code == 201
    pid = proj.json()["id"]
    sha = "a" * 64
    job = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "project_id": pid,
            "source_sha256": sha,
            "attach_gateway_provenance": True,
        },
    )
    assert job.status_code == 201
    body = job.json()
    assert body["provenance"]
    assert "api_key" not in (body["provenance"] or {})
    assert body["provenance"]["model_id"] == BASELINE_MODEL_ID

    upd = client.post(
        f"/api/v1/jobs/{body['id']}/provenance",
        headers=headers,
        json={
            "provenance": {
                "model_id": BASELINE_MODEL_ID,
                "endpoint": "http://x/v1?token=1",
            },
            "api_key": "sk-leak",
        },
    )
    assert upd.status_code == 200
    prov = upd.json()["provenance"]
    assert "api_key" not in prov
    assert "sk-leak" not in str(prov)
    assert "token=" not in (prov.get("endpoint") or "")


def test_api_qa_run_and_block(client):
    headers = {"X-Dev-User": "u", "X-Dev-Tenant": "gw"}
    proj = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"slug": "p2", "name": "P2"},
    )
    pid = proj.json()["id"]
    job = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"project_id": pid, "source_sha256": "b" * 64},
    )
    jid = job.json()["id"]
    r = client.post(
        "/api/v1/qa/run",
        headers=headers,
        json={
            "source_text": "Dose was 10 mg",
            "target_text": "剂量丢失",
            "role": "table",
            "job_id": jid,
            "enable_repair": True,
            "mock_repaired_text": "剂量为 10 mg",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["repaired"] is True
    got = client.get(f"/api/v1/jobs/{jid}", headers=headers)
    assert got.status_code == 200


def test_api_qa_run_rejects_foreign_job(client):
    owner = {"X-Dev-User": "u", "X-Dev-Tenant": "gw"}
    other = {"X-Dev-User": "v", "X-Dev-Tenant": "other"}
    pid = client.post(
        "/api/v1/projects",
        headers=owner,
        json={"slug": "p3", "name": "P3"},
    ).json()["id"]
    jid = client.post(
        "/api/v1/jobs",
        headers=owner,
        json={"project_id": pid, "source_sha256": "c" * 64},
    ).json()["id"]
    r = client.post(
        "/api/v1/qa/run",
        headers=other,
        json={
            "source_text": "Dose was 10 mg",
            "target_text": "剂量丢失",
            "role": "table",
            "job_id": jid,
        },
    )
    assert r.status_code == 404
    still = client.get(f"/api/v1/jobs/{jid}", headers=owner)
    assert still.status_code == 200
    assert still.json()["status"] != "qa_blocked"

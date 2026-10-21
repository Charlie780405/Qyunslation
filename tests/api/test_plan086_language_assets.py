from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base

ADMIN = {"X-Dev-User": "admin", "X-Dev-Tenant": "asset-tenant", "X-Dev-Role": "term_admin"}
USER = {"X-Dev-User": "user", "X-Dev-Tenant": "asset-tenant", "X-Dev-Role": "translator"}
OTHER = {"X-Dev-User": "other", "X-Dev-Tenant": "other-tenant", "X-Dev-Role": "term_admin"}


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


def test_style_profile_publish_creates_immutable_release_and_bundle(client):
    created = client.post(
        "/api/v1/style-profiles",
        headers=ADMIN,
        json={
            "name": "临床研究中文",
            "src_lang": "en",
            "tgt_lang": "zh",
            "document_profile": "临床研究文档",
            "rules": [{"code": "STYLE-001", "text": "药品名称首次出现保留英文通用名"}],
        },
    )
    assert created.status_code == 201, created.text
    profile = created.json()
    published = client.post(f"/api/v1/style-profiles/{profile['id']}/publish", headers=ADMIN)
    assert published.status_code == 200, published.text
    release = published.json()["release"]
    assert release["asset_type"] == "style"
    assert release["status"] == "published"

    releases = client.get("/api/v1/language-assets/releases?asset_type=style", headers=USER)
    assert releases.status_code == 200
    assert releases.json()["items"][0]["id"] == release["id"]

    from qyunslation.language_assets import build_language_asset_bundle
    from qyunslation.persist.db import SessionLocal

    with SessionLocal() as session:
        tenant = session.query(__import__("qyunslation.persist.models", fromlist=["Tenant"]).Tenant).filter_by(slug="asset-tenant").one()
        bundle = build_language_asset_bundle(
            session,
            tenant_id=tenant.id,
            project_id=None,
            src_lang="en",
            tgt_lang="zh",
            document_profile="临床研究文档",
        )
    assert bundle["style"]["rules"][0]["code"] == "STYLE-001"
    assert bundle["bundle_hash"]


def test_controlled_import_preview_apply_and_publish_is_idempotent(client):
    content = "source,target,domain,risk,forbidden\nprimary endpoint,主要终点,clinical,high,主要终点评估\n"
    preview = client.post(
        "/api/v1/language-assets/imports/preview",
        headers=ADMIN,
        json={
            "asset_type": "termbase",
            "filename": "terms.csv",
            "content": content,
            "license": "internal",
            "provenance": "expert-gold",
            "scope": "tenant",
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["row_count"] == 1
    batch_id = preview.json()["batch_id"]
    applied = client.post(f"/api/v1/language-assets/imports/{batch_id}/apply", headers=ADMIN)
    assert applied.status_code == 201, applied.text
    release = applied.json()["release"]
    assert release["status"] == "draft"
    published = client.post(f"/api/v1/language-assets/releases/{release['id']}/publish", headers=ADMIN)
    assert published.status_code == 200
    from qyunslation.glossary.termbase import runtime_termbase_version
    from qyunslation.persist.db import SessionLocal
    from qyunslation.persist.models import Tenant

    with SessionLocal() as session:
        tenant = session.query(Tenant).filter_by(slug="asset-tenant").one()
        version = runtime_termbase_version(session, tenant_id=tenant.id, project_id=None)
    assert version.startswith("058-")
    detail = client.get(f"/api/v1/language-assets/releases/{release['id']}", headers=USER)
    assert detail.status_code == 200
    assert detail.json()["items"][0]["payload"]["source"] == "primary endpoint"

    again = client.post(f"/api/v1/language-assets/imports/{batch_id}/apply", headers=ADMIN)
    assert again.status_code == 200
    assert again.json()["release"]["id"] == release["id"]
    rolled = client.post(f"/api/v1/language-assets/releases/{release['id']}/rollback", headers=ADMIN)
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["release"]["version"] > release["version"]
    resolved = client.post(
        "/api/v1/terms/resolve",
        headers=USER,
        json={"source_text": "The primary endpoint was met."},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["matches"][0]["target_term"] == "主要终点"


def test_language_assets_are_tenant_isolated_and_invalid_import_is_rejected(client):
    denied = client.post(
        "/api/v1/style-profiles",
        headers=USER,
        json={"name": "nope", "rules": []},
    )
    assert denied.status_code == 403
    bad = client.post(
        "/api/v1/language-assets/imports/preview",
        headers=ADMIN,
        json={"asset_type": "termbase", "filename": "bad.csv", "content": "source\n"},
    )
    assert bad.status_code == 422
    other = client.get("/api/v1/language-assets/releases", headers=OTHER)
    assert other.status_code == 200
    assert other.json()["items"] == []


def test_pitfall_rules_are_data_only_and_deterministic():
    from qyunslation.language_assets import check_pitfall_rules

    findings = check_pitfall_rules(
        {"pitfall": {"rules": [{"code": "P-1", "trigger": "不推荐译法", "severity": "blocker", "detector": "deterministic"}]}},
        "这是一条不推荐译法。",
    )
    assert findings[0].code == "ASSET_PITFALL_TRIGGER"
    assert findings[0].severity == "blocker"


def test_asset_block_is_bounded_and_injected_as_reviewed_data():
    from qyunslation.language_assets import render_prompt_asset_block

    block = render_prompt_asset_block(
        {
            "termbase": {"items": [{"source": "endpoint", "target": "终点", "forbidden": ["端点"]}]},
            "style": {"rules": [{"text": "使用简体中文全角标点"}]},
            "pitfall": {"rules": [{"trigger": "端点", "remediation": "终点"}]},
        }
    )
    assert "批准术语" in block and "禁用：端点" in block
    assert "风格规则" in block and "错法提醒" in block

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from qyunslation.auth import bff
from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, OidcLoginState, WebSession


@pytest.fixture()
def client(monkeypatch):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_COOKIE_SECURE", "0")
    monkeypatch.setenv("QYUNSLATION_OIDC_ISSUER", "https://id.example.test")
    monkeypatch.setenv("QYUNSLATION_OIDC_CLIENT_ID", "qyunslation-web")
    monkeypatch.setenv("QYUNSLATION_SESSION_KEY", "test-session-key")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(bff.router)
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def test_login_uses_server_state_and_pkce(client, monkeypatch):
    async def discover():
        return {"authorization_endpoint": "https://id.example.test/authorize"}

    monkeypatch.setattr(bff, "_discover", discover)
    response = client.get(
        "/auth/login?format=json&return_to=https://evil.example/steal",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    location = response.json()["location"]
    query = parse_qs(urlparse(location).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"][0].endswith("/auth/callback")
    assert "tenant" in query["scope"][0].split()
    assert "roles" in query["scope"][0].split()
    assert response.json()["return_to"] == "/next/workbench"
    state = query["state"][0]
    from qyunslation.persist import db

    with db.SessionLocal() as session:
        row = session.scalar(select(OidcLoginState))
        assert row is not None
        assert row.return_to == "/next/workbench"
        assert row.code_verifier
        assert row.nonce
        assert row.state_hash != state


def test_callback_issues_opaque_session_and_logout_revokes_it(client, monkeypatch):
    async def discover():
        return {
            "token_endpoint": "https://id.example.test/token",
            "userinfo_endpoint": "https://id.example.test/userinfo",
            "authorization_endpoint": "https://id.example.test/authorize",
        }

    async def exchange(metadata, *, code, verifier, redirect_uri):
        assert code == "auth-code"
        assert verifier
        return {"access_token": "opaque-access", "id_token": "verified-id", "token_type": "Bearer"}

    async def userinfo(metadata, access_token):
        assert access_token == "opaque-access"
        return {
            "sub": "user-1",
            "tenant": "acme",
            "name": "Alice",
            "roles": ["reviewer", "workbench_v2"],
        }

    monkeypatch.setattr(bff, "_discover", discover)
    monkeypatch.setattr(bff, "_token_exchange", exchange)
    monkeypatch.setattr(
        bff,
        "_verify_id_token",
        lambda token, metadata, *, expected_nonce: {"sub": "user-1", "tenant": "acme", "nonce": expected_nonce},
    )
    monkeypatch.setattr(bff, "_userinfo", userinfo)
    login = client.get("/auth/login?format=json", follow_redirects=False)
    state = parse_qs(urlparse(login.json()["location"]).query)["state"][0]
    callback = client.get(f"/auth/callback?code=auth-code&state={state}", follow_redirects=False)
    assert callback.status_code == 302
    assert callback.headers["location"] == "/next/workbench"
    assert "qyunslation_session=" in callback.headers["set-cookie"]
    assert "HttpOnly" in callback.headers["set-cookie"]
    assert "qyunslation_csrf=" in callback.headers["set-cookie"]

    me = client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["display_name"] == "Alice"
    assert me.json()["roles"] == ["reviewer"]
    assert me.json()["capabilities"]["workbench_v2"] is True
    csrf = client.cookies.get("qyunslation_csrf")
    assert client.put("/api/v1/preferences", json={"preferences": {"density": "compact"}}).status_code == 403
    assert client.put(
        "/api/v1/preferences",
        headers={"X-CSRF-Token": csrf},
        json={"preferences": {"density": "compact"}},
    ).status_code == 200

    from qyunslation.persist import db

    with db.SessionLocal() as session:
        row = session.scalar(select(WebSession))
        assert row is not None
        assert row.user_sub == "user-1"
        assert row.tenant_slug == "acme"
        assert row.roles == ["reviewer", "workbench_v2"]
        assert row.token_blob and "opaque-access" not in row.token_blob

    logout = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 204
    with db.SessionLocal() as session:
        row = session.scalar(select(WebSession))
        assert row is not None and row.revoked_at is not None


def test_logout_rejects_missing_csrf_for_cookie_session(client, monkeypatch):
    # A synthetic cookie is enough to exercise the double-submit guard before
    # any session lookup; the endpoint must not silently accept browser writes.
    client.cookies.set("qyunslation_session", "opaque")
    client.cookies.set("qyunslation_csrf", "expected")
    response = client.post("/auth/logout")
    assert response.status_code == 403


def test_id_token_uses_discovery_issuer_with_trailing_slash(monkeypatch):
    seen: dict[str, str] = {}

    class _Key:
        key = object()

    class _Client:
        def get_signing_key_from_jwt(self, _token):
            return _Key()

    def decode(_token, _key, *, algorithms, audience, issuer, options):
        seen["issuer"] = issuer
        return {"sub": "user-1", "nonce": "nonce"}

    monkeypatch.setenv("QYUNSLATION_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("QYUNSLATION_OIDC_JWKS_URL", "http://127.0.0.1:9000/jwks")

    def make_client(url, **_kwargs):
        seen["jwks_url"] = url
        return _Client()

    monkeypatch.setattr(bff, "PyJWKClient", make_client)
    monkeypatch.setattr(bff.jwt, "decode", decode)

    bff._verify_id_token(
        "id-token",
        {
            "jwks_uri": "https://issuer.example/jwks",
            "issuer": "https://issuer.example/application/o/qyunslation/",
        },
        expected_nonce="nonce",
    )

    assert seen["issuer"] == "https://issuer.example/application/o/qyunslation/"
    assert seen["jwks_url"] == "http://127.0.0.1:9000/jwks"

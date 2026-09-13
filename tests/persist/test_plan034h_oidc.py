# SPDX-License-Identifier: MPL-2.0
"""PLAN-034h：OIDC / Dev 旁路互斥。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from qyunslation.persist.identity import (
    DevBypassAdapter,
    OidcAdapter,
    clear_jwks_cache,
    resolve_identity,
)


def _make_request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/health",
        "raw_path": b"/api/v1/health",
        "query_string": b"",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in headers.items()
        ],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_jwks_cache()
    yield
    clear_jwks_cache()


def test_production_forbids_dev_bypass(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENV", "production")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    req = _make_request({"X-Dev-User": "x", "X-Dev-Tenant": "t"})
    with pytest.raises(HTTPException) as ei:
        resolve_identity(req)
    assert ei.value.status_code == 403


def test_production_dev_adapter_direct(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENV", "production")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    with pytest.raises(HTTPException) as ei:
        DevBypassAdapter().resolve(_make_request({}))
    assert ei.value.status_code == 403


def test_oidc_missing_bearer(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.delenv("QYUNSLATION_DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setenv("QYUNSLATION_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("QYUNSLATION_OIDC_AUDIENCE", "qyunslation")
    monkeypatch.setenv("QYUNSLATION_OIDC_JWKS_URL", "https://issuer.example/jwks")
    with pytest.raises(HTTPException) as ei:
        resolve_identity(_make_request({}))
    assert ei.value.status_code == 401


def test_oidc_missing_config(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.delenv("QYUNSLATION_DEV_AUTH_BYPASS", raising=False)
    monkeypatch.delenv("QYUNSLATION_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("QYUNSLATION_OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("QYUNSLATION_OIDC_JWKS_URL", raising=False)
    with pytest.raises(HTTPException) as ei:
        OidcAdapter().resolve(_make_request({"Authorization": "Bearer x"}))
    assert ei.value.status_code == 503


def test_oidc_forged_token(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.delenv("QYUNSLATION_DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setenv("QYUNSLATION_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("QYUNSLATION_OIDC_AUDIENCE", "qyunslation")
    monkeypatch.setenv("QYUNSLATION_OIDC_JWKS_URL", "https://issuer.example/jwks")

    def boom(token, cfg):
        raise jwt.InvalidTokenError("forged")

    adapter = OidcAdapter(decode_hook=boom)
    with pytest.raises(HTTPException) as ei:
        adapter.resolve(_make_request({"Authorization": "Bearer forged.jwt.here"}))
    assert ei.value.status_code == 401


def test_oidc_valid_token_via_hook(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.delenv("QYUNSLATION_DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setenv("QYUNSLATION_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("QYUNSLATION_OIDC_AUDIENCE", "qyunslation")
    monkeypatch.setenv("QYUNSLATION_OIDC_JWKS_URL", "https://issuer.example/jwks")
    monkeypatch.setenv("QYUNSLATION_OIDC_TENANT_CLAIM", "tenant")

    def decode(token, cfg):
        assert token == "good-token"
        return {"sub": "user-1", "tenant": "acme", "iss": cfg["issuer"], "aud": cfg["audience"]}

    adapter = OidcAdapter(decode_hook=decode)
    ctx = adapter.resolve(_make_request({"Authorization": "Bearer good-token"}))
    assert ctx.user_sub == "user-1"
    assert ctx.tenant_slug == "acme"


def test_oidc_missing_tenant_claim_is_401(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("QYUNSLATION_OIDC_AUDIENCE", "qyunslation")
    monkeypatch.setenv("QYUNSLATION_OIDC_JWKS_URL", "https://issuer.example/jwks")

    def decode(token, cfg):
        return {"sub": "user-2"}

    adapter = OidcAdapter(decode_hook=decode)
    with pytest.raises(HTTPException) as ei:
        adapter.resolve(
            _make_request({"Authorization": "Bearer t", "X-Tenant": "from-header"})
        )
    assert ei.value.status_code == 401
    assert "tenant" in str(ei.value.detail).lower()


def test_oidc_ignores_x_tenant_when_claim_present(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("QYUNSLATION_OIDC_AUDIENCE", "qyunslation")
    monkeypatch.setenv("QYUNSLATION_OIDC_JWKS_URL", "https://issuer.example/jwks")

    def decode(token, cfg):
        return {"sub": "user-3", "tenant": "from-jwt"}

    adapter = OidcAdapter(decode_hook=decode)
    ctx = adapter.resolve(
        _make_request({"Authorization": "Bearer t", "X-Tenant": "spoofed"})
    )
    assert ctx.tenant_slug == "from-jwt"


def test_dev_bypass_still_works_non_production(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    ctx = resolve_identity(_make_request({"X-Dev-User": "alice", "X-Dev-Tenant": "t1"}))
    assert ctx.user_sub == "alice"
    assert ctx.tenant_slug == "t1"


def test_rsa_jwt_roundtrip_with_real_decode(monkeypatch):
    """用本机 RSA 钥签发 + decode_hook 外的真实 jwt.decode 路径（注入 signing key）。"""
    monkeypatch.setenv("QYUNSLATION_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("QYUNSLATION_OIDC_AUDIENCE", "qyunslation")
    monkeypatch.setenv("QYUNSLATION_OIDC_JWKS_URL", "https://issuer.example/jwks")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "rsa-user",
            "tenant": "rsa-tenant",
            "iss": "https://issuer.example",
            "aud": "qyunslation",
            "exp": now + timedelta(hours=1),
            "iat": now,
        },
        key,
        algorithm="RS256",
    )

    class _Key:
        def __init__(self, k):
            self.key = k.public_key()

    class _Client:
        def get_signing_key_from_jwt(self, _token):
            return _Key(key)

    adapter = OidcAdapter(jwks_client_factory=lambda _url: _Client())
    ctx = adapter.resolve(_make_request({"Authorization": f"Bearer {token}"}))
    assert ctx.user_sub == "rsa-user"
    assert ctx.tenant_slug == "rsa-tenant"

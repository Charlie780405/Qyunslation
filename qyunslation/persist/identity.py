# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c/h：身份适配器（Dev 旁路 + OIDC JWT/JWKS）。"""
from __future__ import annotations

import os
import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import select

OIDC_ISSUER_ENV = "QYUNSLATION_OIDC_ISSUER"
OIDC_AUDIENCE_ENV = "QYUNSLATION_OIDC_AUDIENCE"
OIDC_JWKS_URL_ENV = "QYUNSLATION_OIDC_JWKS_URL"
OIDC_TENANT_CLAIM_ENV = "QYUNSLATION_OIDC_TENANT_CLAIM"
WEB_SESSION_COOKIE = "qyunslation_session"
CSRF_COOKIE = "qyunslation_csrf"
SESSION_IDLE_MINUTES_ENV = "QYUNSLATION_SESSION_IDLE_MINUTES"


@dataclass(frozen=True)
class IdentityContext:
    tenant_slug: str
    user_sub: str
    display_name: str | None = None
    roles: tuple[str, ...] = ()
    auth_method: str = "bearer"


class IdentityAdapter(Protocol):
    def resolve(self, request: Request) -> IdentityContext: ...


def _env_name() -> str:
    return (os.environ.get("QYUNSLATION_ENV") or "development").strip().lower()


def _is_production() -> bool:
    return _env_name() == "production"


def _dev_bypass_enabled() -> bool:
    flag = (os.environ.get("QYUNSLATION_DEV_AUTH_BYPASS") or "").strip()
    return flag in {"1", "true", "TRUE", "yes", "YES"}


def _session_idle_minutes() -> float:
    try:
        value = float((os.environ.get(SESSION_IDLE_MINUTES_ENV) or "60").strip())
    except ValueError:
        value = 60.0
    return max(value, 1.0)


class DevBypassAdapter:
    """仅非 production 且显式旁路开关时可用。"""

    def resolve(self, request: Request) -> IdentityContext:
        if _is_production():
            raise HTTPException(status_code=403, detail="dev auth bypass disabled in production")
        if not _dev_bypass_enabled():
            raise HTTPException(status_code=401, detail="dev auth bypass not enabled")
        user = (request.headers.get("X-Dev-User") or "dev-user").strip() or "dev-user"
        tenant = (request.headers.get("X-Dev-Tenant") or "dev").strip() or "dev"
        role_header = (request.headers.get("X-Dev-Role") or "").strip()
        roles = tuple(
            part.strip()
            for part in role_header.replace(";", ",").split(",")
            if part.strip()
        ) or ("translator", "workbench_v2")
        return IdentityContext(tenant_slug=tenant, user_sub=user, roles=roles)


_JWKS_CACHE: dict[str, tuple[float, PyJWKClient]] = {}
_JWKS_TTL_SEC = 300.0


def clear_jwks_cache() -> None:
    _JWKS_CACHE.clear()


def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    now = time.monotonic()
    hit = _JWKS_CACHE.get(jwks_url)
    if hit and (now - hit[0]) < _JWKS_TTL_SEC:
        return hit[1]
    client = PyJWKClient(jwks_url, cache_keys=True, lifespan=int(_JWKS_TTL_SEC))
    _JWKS_CACHE[jwks_url] = (now, client)
    return client


def _oidc_config() -> dict[str, str]:
    issuer = (os.environ.get(OIDC_ISSUER_ENV) or "").strip()
    audience = (os.environ.get(OIDC_AUDIENCE_ENV) or "").strip()
    jwks_url = (os.environ.get(OIDC_JWKS_URL_ENV) or "").strip()
    tenant_claim = (os.environ.get(OIDC_TENANT_CLAIM_ENV) or "tenant").strip() or "tenant"
    return {
        "issuer": issuer,
        "audience": audience,
        "jwks_url": jwks_url,
        "tenant_claim": tenant_claim,
    }


class OidcAdapter:
    """Bearer JWT + JWKS 验签；缺配置返回明确错误，不静默回 Dev。"""

    def __init__(
        self,
        *,
        jwks_client_factory: Callable[[str], Any] | None = None,
        decode_hook: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self._jwks_client_factory = jwks_client_factory or _get_jwk_client
        self._decode_hook = decode_hook

    def resolve(self, request: Request) -> IdentityContext:
        cfg = _oidc_config()
        if not cfg["issuer"] or not cfg["audience"] or not cfg["jwks_url"]:
            raise HTTPException(
                status_code=503,
                detail=(
                    "OIDC not configured: set "
                    f"{OIDC_ISSUER_ENV}, {OIDC_AUDIENCE_ENV}, {OIDC_JWKS_URL_ENV}"
                ),
            )
        auth = (request.headers.get("Authorization") or "").strip()
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing Bearer token")
        token = auth[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="empty Bearer token")

        try:
            if self._decode_hook is not None:
                claims = self._decode_hook(token, cfg)
            else:
                client = self._jwks_client_factory(cfg["jwks_url"])
                signing_key = client.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "ES256"],
                    audience=cfg["audience"],
                    issuer=cfg["issuer"],
                    options={"require": ["exp", "sub"]},
                )
        except HTTPException:
            raise
        except Exception as exc:
            # 不回显验签异常原文（可能含 issuer/kid/JWKS 细节）
            raise HTTPException(status_code=401, detail="invalid token") from exc

        sub = str(claims.get("sub") or "").strip()
        if not sub:
            raise HTTPException(status_code=401, detail="token missing sub")
        tenant_raw = claims.get(cfg["tenant_claim"])
        tenant = str(tenant_raw or "").strip()
        if not tenant:
            raise HTTPException(status_code=401, detail="token missing tenant")
        return IdentityContext(tenant_slug=tenant, user_sub=sub)


def _resolve_web_session(request: Request) -> IdentityContext | None:
    """Resolve an opaque BFF cookie without ever accepting client claims."""
    raw = (request.cookies.get(WEB_SESSION_COOKIE) or "").strip()
    if not raw:
        return None
    from qyunslation.persist import db as persist_db
    from qyunslation.persist.models import WebSession

    if persist_db.SessionLocal is None:
        raise HTTPException(status_code=503, detail="web session store unavailable")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    with persist_db.SessionLocal() as session:
        row = session.scalar(select(WebSession).where(WebSession.session_hash == digest))
        if row is None or row.revoked_at is not None:
            return None
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=now.tzinfo)
        idle_cutoff = now.timestamp() - (_session_idle_minutes() * 60)
        last_seen = row.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=now.tzinfo)
        if expires_at <= now or last_seen.timestamp() < idle_cutoff:
            return None
        row.last_seen_at = now
        session.commit()
        return IdentityContext(
            tenant_slug=row.tenant_slug,
            user_sub=row.user_sub,
            display_name=row.display_name,
            roles=tuple(str(item) for item in (row.roles or []) if str(item).strip()),
            auth_method="bff_session",
        )


def require_csrf(request: Request) -> None:
    """Require the double-submit CSRF token for cookie-authenticated writes."""
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    if not request.cookies.get(WEB_SESSION_COOKIE):
        return
    cookie = (request.cookies.get(CSRF_COOKIE) or "").strip()
    header = (request.headers.get("X-CSRF-Token") or "").strip()
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF token required")


def resolve_identity(request: Request) -> IdentityContext:
    """production 强制 OIDC；非 production 且 bypass → Dev；否则 OIDC。"""
    session_identity = _resolve_web_session(request)
    if session_identity is not None:
        return session_identity
    if _is_production():
        if _dev_bypass_enabled():
            # 显式拒绝：即使开了 bypass 也不走 Dev
            raise HTTPException(status_code=403, detail="dev auth bypass disabled in production")
        return OidcAdapter().resolve(request)
    if _dev_bypass_enabled():
        return DevBypassAdapter().resolve(request)
    return OidcAdapter().resolve(request)

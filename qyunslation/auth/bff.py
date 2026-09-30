# SPDX-License-Identifier: MPL-2.0
"""PLAN-066c: OIDC Authorization Code + PKCE BFF session boundary.

The browser never receives an OIDC access or refresh token.  The authorization
request is bound to a short-lived database row and the callback exchanges it
server-side before issuing an opaque, HttpOnly session cookie.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from jwt import PyJWKClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from qyunslation.api.v1 import get_db
from qyunslation.persist.identity import (
    CSRF_COOKIE,
    WEB_SESSION_COOKIE,
    require_csrf,
)
from qyunslation.persist.models import OidcLoginState, WebSession

router = APIRouter(tags=["Authentication"])

OIDC_ISSUER_ENV = "QYUNSLATION_OIDC_ISSUER"
OIDC_CLIENT_ID_ENV = "QYUNSLATION_OIDC_CLIENT_ID"
OIDC_CLIENT_SECRET_ENV = "QYUNSLATION_OIDC_CLIENT_SECRET"
OIDC_REDIRECT_URI_ENV = "QYUNSLATION_OIDC_REDIRECT_URI"
OIDC_TENANT_CLAIM_ENV = "QYUNSLATION_OIDC_TENANT_CLAIM"
SESSION_KEY_ENV = "QYUNSLATION_SESSION_KEY"
SESSION_IDLE_MINUTES_ENV = "QYUNSLATION_SESSION_IDLE_MINUTES"
SESSION_ABSOLUTE_HOURS_ENV = "QYUNSLATION_SESSION_ABSOLUTE_HOURS"
COOKIE_SECURE_ENV = "QYUNSLATION_COOKIE_SECURE"

_STATE_TTL = timedelta(minutes=10)
_DEFAULT_IDLE_MINUTES = 60
_DEFAULT_ABSOLUTE_HOURS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_return_to(value: str | None) -> str:
    candidate = (value or "/next/workbench").strip()
    # Only same-origin absolute paths are allowed.  In particular, reject
    # scheme-relative URLs such as //evil.example/path.
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/next/workbench"
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or "\\" in candidate:
        return "/next/workbench"
    return candidate[:512]


def _env_float(name: str, default: float, *, minimum: float = 1) -> float:
    try:
        value = float((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default
    return max(value, minimum)


def _issuer() -> str:
    return (os.environ.get(OIDC_ISSUER_ENV) or "").strip().rstrip("/")


def _client_id() -> str:
    return (os.environ.get(OIDC_CLIENT_ID_ENV) or "").strip()


def _session_key() -> str:
    return (os.environ.get(SESSION_KEY_ENV) or "").strip()


def _secure_cookie() -> bool:
    raw = (os.environ.get(COOKIE_SECURE_ENV) or "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    return (os.environ.get("QYUNSLATION_ENV") or "development").strip().lower() == "production"


def _redirect_uri(request: Request) -> str:
    configured = (os.environ.get(OIDC_REDIRECT_URI_ENV) or "").strip()
    if configured:
        return configured
    return str(request.base_url).rstrip("/") + "/auth/callback"


def _require_login_config() -> None:
    missing = [name for name, value in ((OIDC_ISSUER_ENV, _issuer()), (OIDC_CLIENT_ID_ENV, _client_id())) if not value]
    if missing:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SSO_NOT_CONFIGURED",
                "message": "公司身份服务尚未配置，请联系系统管理员。",
                "missing": missing,
            },
        )
    if not _session_key():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BFF_SESSION_NOT_CONFIGURED",
                "message": "安全会话密钥尚未配置，请联系系统管理员。",
            },
        )


async def _discover() -> dict[str, str]:
    issuer = _issuer()
    if not issuer:
        raise HTTPException(status_code=503, detail="OIDC issuer is not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(f"{issuer}/.well-known/openid-configuration")
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="无法读取公司身份服务配置") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="公司身份服务配置无效")
    return {str(key): str(value) for key, value in body.items() if value is not None}


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _fernet() -> Fernet:
    key = _session_key()
    if not key:
        raise HTTPException(status_code=503, detail="BFF session encryption is not configured")
    derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode("utf-8")).digest())
    return Fernet(derived)


def _encrypt_token_set(tokens: dict) -> str:
    # JSON is encrypted before it reaches the database; no token is returned
    # in a response or written to application logs.
    payload = json.dumps(tokens, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def _verify_id_token(
    id_token: str,
    metadata: dict[str, str],
    *,
    expected_nonce: str,
) -> dict:
    jwks_uri = metadata.get("jwks_uri")
    if not jwks_uri:
        raise HTTPException(status_code=502, detail="身份服务缺少 JWKS 配置")
    try:
        signing_key = PyJWKClient(jwks_uri, cache_keys=True, lifespan=300).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=_client_id(),
            issuer=_issuer(),
            options={"require": ["exp", "sub", "nonce"]},
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="身份服务返回的 ID token 无效") from exc
    if not secrets.compare_digest(str(claims.get("nonce") or ""), expected_nonce):
        raise HTTPException(status_code=401, detail="OIDC nonce 校验失败")
    return claims


def _roles_from_claims(claims: dict) -> list[str]:
    raw = claims.get("roles", claims.get("role", []))
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    allowed = {
        "translator",
        "reviewer",
        "termbase_admin",
        "system_admin",
        "admin",
        "owner",
        # Authentik maps the qyunslation-vue-beta group to this capability.
        # It is retained in the server-side session roles but is not a
        # persistence role and therefore cannot grant tenant permissions.
        "workbench_v2",
    }
    return sorted({str(item).strip() for item in raw if str(item).strip() in allowed})


async def _token_exchange(
    metadata: dict[str, str],
    *,
    code: str,
    verifier: str,
    redirect_uri: str,
) -> dict:
    endpoint = metadata.get("token_endpoint")
    if not endpoint:
        raise HTTPException(status_code=502, detail="身份服务缺少 token endpoint")
    data = {
        "grant_type": "authorization_code",
        "client_id": _client_id(),
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    secret = (os.environ.get(OIDC_CLIENT_SECRET_ENV) or "").strip()
    if secret:
        data["client_secret"] = secret
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.post(endpoint, data=data)
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="无法完成公司身份登录") from exc
    if not isinstance(body, dict) or not body.get("access_token") or not body.get("id_token"):
        raise HTTPException(status_code=502, detail="身份服务返回的登录凭据不完整")
    return body


async def _userinfo(metadata: dict[str, str], access_token: str) -> dict:
    endpoint = metadata.get("userinfo_endpoint")
    if not endpoint:
        raise HTTPException(status_code=502, detail="身份服务缺少 userinfo endpoint")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(endpoint, headers={"Authorization": f"Bearer {access_token}"})
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="无法读取公司身份信息") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="公司身份信息格式无效")
    return body


def _set_auth_cookies(response: Response, *, session_id: str, csrf: str, max_age: int) -> None:
    secure = _secure_cookie()
    response.set_cookie(
        WEB_SESSION_COOKIE,
        session_id,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


@router.get("/auth/login", include_in_schema=False)
async def auth_login(
    request: Request,
    return_to: str = Query("/next/workbench"),
    format: str = Query("redirect"),
    session: Session = Depends(get_db),
):
    try:
        _require_login_config()
    except HTTPException as exc:
        if format.casefold() == "json" and isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        raise
    metadata = await _discover()
    authorization_endpoint = metadata.get("authorization_endpoint")
    if not authorization_endpoint:
        raise HTTPException(status_code=502, detail="身份服务缺少 authorization endpoint")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    session.query(OidcLoginState).filter(OidcLoginState.expires_at < _now()).delete(
        synchronize_session=False
    )
    session.add(
        OidcLoginState(
            state_hash=_state_hash(state),
            code_verifier=verifier,
            nonce=nonce,
            return_to=_safe_return_to(return_to),
            expires_at=_now() + _STATE_TTL,
        )
    )
    session.flush()
    query = urlencode(
        {
            "client_id": _client_id(),
            "response_type": "code",
            "redirect_uri": _redirect_uri(request),
            "scope": "openid profile email roles",
            "state": state,
            "nonce": nonce,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    location = f"{authorization_endpoint}?{query}"
    if format.casefold() == "json":
        return JSONResponse({"location": location, "return_to": _safe_return_to(return_to)})
    return RedirectResponse(location, status_code=302)


@router.get("/auth/callback", include_in_schema=False)
async def auth_callback(
    request: Request,
    code: str = Query(""),
    state: str = Query(""),
    session: Session = Depends(get_db),
):
    _require_login_config()
    if not code.strip() or not state.strip():
        raise HTTPException(status_code=400, detail="OIDC callback 缺少 code 或 state")
    row = session.scalar(select(OidcLoginState).where(OidcLoginState.state_hash == _state_hash(state)))
    expires_at = row.expires_at if row is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if row is None or expires_at <= _now():
        raise HTTPException(status_code=400, detail="OIDC 登录状态已失效，请重新登录")
    return_to = _safe_return_to(row.return_to)
    verifier, nonce = row.code_verifier, row.nonce
    session.delete(row)
    session.flush()
    metadata = await _discover()
    tokens = await _token_exchange(
        metadata,
        code=code,
        verifier=verifier,
        redirect_uri=_redirect_uri(request),
    )
    id_claims = _verify_id_token(tokens["id_token"], metadata, expected_nonce=nonce)
    user_claims = await _userinfo(metadata, tokens["access_token"])
    if str(user_claims.get("sub") or "") != str(id_claims.get("sub") or ""):
        raise HTTPException(status_code=401, detail="身份服务用户标识不一致")
    tenant_claim = (os.environ.get(OIDC_TENANT_CLAIM_ENV) or "tenant").strip() or "tenant"
    tenant = str(user_claims.get(tenant_claim) or id_claims.get(tenant_claim) or "").strip()
    user_sub = str(user_claims.get("sub") or id_claims.get("sub") or "").strip()
    if not tenant or not user_sub:
        raise HTTPException(status_code=401, detail="身份服务缺少租户或用户标识")
    roles = _roles_from_claims({**id_claims, **user_claims})
    now = _now()
    absolute_hours = _env_float(SESSION_ABSOLUTE_HOURS_ENV, _DEFAULT_ABSOLUTE_HOURS, minimum=0.25)
    max_age = int(absolute_hours * 3600)
    raw_session = secrets.token_urlsafe(48)
    session.add(
        WebSession(
            session_hash=hashlib.sha256(raw_session.encode("utf-8")).hexdigest(),
            tenant_slug=tenant,
            user_sub=user_sub,
            display_name=str(
                user_claims.get("name")
                or user_claims.get("preferred_username")
                or user_claims.get("email")
                or user_sub
            )[:256],
            roles=roles,
            token_blob=_encrypt_token_set(tokens),
            expires_at=now + timedelta(seconds=max_age),
            last_seen_at=now,
        )
    )
    csrf = secrets.token_urlsafe(32)
    response = RedirectResponse(return_to, status_code=302)
    _set_auth_cookies(response, session_id=raw_session, csrf=csrf, max_age=max_age)
    return response


@router.post("/auth/logout", include_in_schema=False)
def auth_logout(request: Request, session: Session = Depends(get_db)) -> Response:
    require_csrf(request)
    raw = (request.cookies.get(WEB_SESSION_COOKIE) or "").strip()
    if raw:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        row = session.scalar(select(WebSession).where(WebSession.session_hash == digest))
        if row is not None and row.revoked_at is None:
            row.revoked_at = _now()
    response = Response(status_code=204)
    response.delete_cookie(WEB_SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response

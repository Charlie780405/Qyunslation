# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c：身份适配器（Dev 旁路 + OIDC 桩）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class IdentityContext:
    tenant_slug: str
    user_sub: str


class IdentityAdapter(Protocol):
    def resolve(self, request: Request) -> IdentityContext: ...


def _env_name() -> str:
    return (os.environ.get("QYUNSLATION_ENV") or "development").strip().lower()


def _dev_bypass_enabled() -> bool:
    flag = (os.environ.get("QYUNSLATION_DEV_AUTH_BYPASS") or "").strip()
    return flag in {"1", "true", "TRUE", "yes", "YES"}


class DevBypassAdapter:
    """仅非 production 且显式旁路开关时可用。"""

    def resolve(self, request: Request) -> IdentityContext:
        if _env_name() == "production":
            raise HTTPException(status_code=403, detail="dev auth bypass disabled in production")
        if not _dev_bypass_enabled():
            raise HTTPException(status_code=401, detail="dev auth bypass not enabled")
        user = (request.headers.get("X-Dev-User") or "dev-user").strip() or "dev-user"
        tenant = (request.headers.get("X-Dev-Tenant") or "dev").strip() or "dev"
        return IdentityContext(tenant_slug=tenant, user_sub=user)


class OidcAdapter:
    """034h 收口；本期桩。"""

    def resolve(self, request: Request) -> IdentityContext:
        raise HTTPException(status_code=501, detail="OIDC adapter not implemented (PLAN-034h)")


def resolve_identity(request: Request) -> IdentityContext:
    """优先 Dev 旁路；否则 OIDC 桩。"""
    if _dev_bypass_enabled():
        return DevBypassAdapter().resolve(request)
    return OidcAdapter().resolve(request)

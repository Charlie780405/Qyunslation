# SPDX-License-Identifier: MPL-2.0
"""PLAN-060 loopback HMAC boundary for the Gradio-to-sidecar bridge."""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from collections.abc import Mapping

from fastapi import HTTPException, Request

BRIDGE_SECRET_ENV = "QYUNSLATION_TERM_BRIDGE_SECRET"
BRIDGE_TIMESTAMP_HEADER = "X-Qyunslation-Bridge-Timestamp"
BRIDGE_NONCE_HEADER = "X-Qyunslation-Bridge-Nonce"
BRIDGE_SIGNATURE_HEADER = "X-Qyunslation-Bridge-Signature"
_MAX_CLOCK_SKEW_SECONDS = 60
_NONCE_TTL_SECONDS = 120
_nonce_lock = threading.Lock()
_used_nonces: dict[str, float] = {}


def _secret() -> bytes:
    value = (os.environ.get(BRIDGE_SECRET_ENV) or "").strip()
    if not value:
        raise HTTPException(status_code=503, detail="workbench term bridge unavailable")
    return value.encode("utf-8")


def _signature_payload(*, method: str, path: str, body: bytes, timestamp: str, nonce: str) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return "\n".join((timestamp, nonce, method.upper(), path, body_hash)).encode("utf-8")


def sign_bridge_request(
    *, method: str, path: str, body: bytes, secret: str, nonce: str, timestamp: int
) -> dict[str, str]:
    """Build bridge headers for the trusted GUI process and isolated tests."""
    value = _signature_payload(
        method=method,
        path=path,
        body=body,
        timestamp=str(timestamp),
        nonce=nonce,
    )
    signature = hmac.new(secret.encode("utf-8"), value, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        BRIDGE_TIMESTAMP_HEADER: str(timestamp),
        BRIDGE_NONCE_HEADER: nonce,
        BRIDGE_SIGNATURE_HEADER: signature,
    }


def _is_loopback(host: str | None) -> bool:
    return host in {"127.0.0.1", "::1"}


def _claim_nonce(nonce: str, now: float) -> None:
    with _nonce_lock:
        for key, expires_at in tuple(_used_nonces.items()):
            if expires_at <= now:
                _used_nonces.pop(key, None)
        if nonce in _used_nonces:
            raise HTTPException(status_code=409, detail="workbench bridge request already used")
        _used_nonces[nonce] = now + _NONCE_TTL_SECONDS


def reset_nonce_cache() -> None:
    """Test-only reset; production never exposes nonce cache controls."""
    with _nonce_lock:
        _used_nonces.clear()


async def require_signed_loopback(request: Request) -> None:
    """Reject browser, replayed, stale, or unsigned bridge requests.

    The authenticated Gradio callback signs each server-to-server request.  The
    browser does not receive the secret and cannot choose the tenant boundary.
    """
    if not _is_loopback(getattr(request.client, "host", None)):
        raise HTTPException(status_code=403, detail="workbench bridge is loopback only")
    timestamp = (request.headers.get(BRIDGE_TIMESTAMP_HEADER) or "").strip()
    nonce = (request.headers.get(BRIDGE_NONCE_HEADER) or "").strip()
    supplied = (request.headers.get(BRIDGE_SIGNATURE_HEADER) or "").strip().lower()
    if not timestamp or not nonce or not supplied or len(nonce) > 128:
        raise HTTPException(status_code=401, detail="invalid workbench bridge credentials")
    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid workbench bridge credentials") from exc
    now = time.time()
    if abs(now - timestamp_value) > _MAX_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="expired workbench bridge credentials")
    body = await request.body()
    expected = hmac.new(
        _secret(),
        _signature_payload(
            method=request.method,
            path=request.url.path,
            body=body,
            timestamp=timestamp,
            nonce=nonce,
        ),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="invalid workbench bridge credentials")
    _claim_nonce(nonce, now)

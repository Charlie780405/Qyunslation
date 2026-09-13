#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-034h 本机试点 IdP：只绑 127.0.0.1，发 RS256 JWT + JWKS。

等正式 IdP 就绪后关掉本进程，改 office.env 的 issuer/jwks 即可。
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from jwt import encode as jwt_encode
from jwt.algorithms import RSAAlgorithm

DATA_DIR = Path(os.environ.get("QYUNSLATION_OIDC_DATA_DIR") or "var/oidc")
ISSUER = (os.environ.get("QYUNSLATION_OIDC_ISSUER") or "http://127.0.0.1:5556").rstrip("/")
AUDIENCE = os.environ.get("QYUNSLATION_OIDC_AUDIENCE") or "qyunslation"
MINT_SECRET = (os.environ.get("QYUNSLATION_OIDC_MINT_SECRET") or "").strip()
BIND = os.environ.get("QYUNSLATION_OIDC_BIND") or "127.0.0.1"
PORT = int(os.environ.get("QYUNSLATION_OIDC_PORT") or "5556")
TTL_SEC = int(os.environ.get("QYUNSLATION_OIDC_TTL_SEC") or "3600")
KID = "plan034h-pilot"


def _load_or_create_key() -> tuple[object, dict]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pem_path = DATA_DIR / "pilot-rsa.pem"
    if pem_path.exists():
        private = serialization.load_pem_private_key(pem_path.read_bytes(), password=None)
    else:
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem_path.write_bytes(
            private.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        os.chmod(pem_path, 0o600)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk["kid"] = KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return private, jwk


PRIVATE_KEY, PUBLIC_JWK = _load_or_create_key()


def mint_token(*, sub: str, tenant: str) -> str:
    import time

    now = int(time.time())
    return jwt_encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": sub,
            "tenant": tenant,
            "iat": now,
            "exp": now + TTL_SEC,
        },
        PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": KID},
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: dict | list, *, ctype: str = "application/json") -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] in {"/jwks.json", "/jwks"}:
            self._send(200, {"keys": [PUBLIC_JWK]})
            return
        self._send(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/token":
            self._send(404, {"detail": "not found"})
            return
        if not MINT_SECRET:
            self._send(503, {"detail": "QYUNSLATION_OIDC_MINT_SECRET unset"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        fields = parse_qs(raw.decode("utf-8"))
        secret = (fields.get("secret") or [self.headers.get("X-Mint-Secret") or ""])[0]
        if secret != MINT_SECRET:
            self._send(401, {"detail": "invalid mint secret"})
            return
        sub = (fields.get("sub") or ["pilot-user"])[0].strip() or "pilot-user"
        tenant = (fields.get("tenant") or ["pilot"])[0].strip() or "pilot"
        token = mint_token(sub=sub, tenant=tenant)
        self._send(200, {"access_token": token, "token_type": "Bearer", "expires_in": TTL_SEC})


def main() -> int:
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    sys.stderr.write("plan034h-pilot-oidc %s jwks=%s/jwks.json\n" % (ISSUER, ISSUER))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

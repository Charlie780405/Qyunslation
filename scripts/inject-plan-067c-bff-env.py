#!/usr/bin/env python3
"""Safely inject the PLAN-067c BFF settings into the protected sidecar env.

The command is read-only by default. Production mutation requires ``--apply``
and a resolvable public Authentik hostname so a partially configured sidecar is
not restarted by accident. Secret values are never printed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import secrets
import shutil
import socket
import sys
import tempfile
from pathlib import Path


KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*?)(\r?\n)?$")
DEFAULT_REDIRECT = "https://translate.qyunsgen.com/auth/callback"


def read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    values: dict[str, str] = {}
    for line in lines:
        match = KEY_RE.match(line)
        if match:
            key, value = match.group(1), match.group(2)
            if key in values:
                raise ValueError(f"duplicate key in {path}: {key}")
            values[key] = value
    return lines, values


def assert_private_file(path: Path) -> None:
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        raise ValueError(f"{path} must have mode 0600 (found {mode:04o})")


def resolve_public_host(host: str) -> None:
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RuntimeError(f"public Authentik host does not resolve: {host}") from exc


def replace_or_append(lines: list[str], key: str, value: str) -> None:
    replacement = f"{key}={value}\n"
    for index, line in enumerate(lines):
        match = KEY_RE.match(line)
        if match and match.group(1) == key:
            lines[index] = replacement
            return
    if lines and not lines[-1].endswith("\n"):
        lines.append("\n")
    lines.append(replacement)


def atomic_write(path: Path, content: str) -> None:
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        tmp.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path("/home/dev/pdf2zh/office.env"))
    parser.add_argument("--authentik-env", type=Path, default=Path("deploy/authentik/.env"))
    parser.add_argument("--auth-host", default="auth.qyunsgen.com")
    parser.add_argument("--apply", action="store_true", help="atomically update the protected env")
    parser.add_argument(
        "--skip-dns",
        action="store_true",
        help="test-only bypass; never use for production injection",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        assert_private_file(args.env_file)
        assert_private_file(args.authentik_env)
        lines, current = read_env(args.env_file)
        _, idp = read_env(args.authentik_env)
        client_id = idp.get("QYUNSLATION_OIDC_CLIENT_ID", "").strip()
        client_secret = idp.get("QYUNSLATION_OIDC_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise ValueError("Authentik client ID and confidential client secret are required")
        if current.get("QYUNSLATION_OIDC_CLIENT_ID", client_id).strip() not in {"", client_id}:
            raise ValueError("existing QYUNSLATION_OIDC_CLIENT_ID differs from Authentik")
        if not args.skip_dns:
            resolve_public_host(args.auth_host)
        elif args.apply:
            print("WARNING: --skip-dns is intended only for isolated tests", file=sys.stderr)

        session_key = current.get("QYUNSLATION_SESSION_KEY", "").strip() or secrets.token_urlsafe(48)
        desired = {
            "QYUNSLATION_OIDC_CLIENT_ID": client_id,
            "QYUNSLATION_OIDC_CLIENT_SECRET": client_secret,
            "QYUNSLATION_OIDC_REDIRECT_URI": DEFAULT_REDIRECT,
            "QYUNSLATION_SESSION_KEY": session_key,
            "QYUNSLATION_ENV": "production",
        }
        if not args.apply:
            print("DRY RUN: public DNS gate passed; would update: " + ", ".join(sorted(desired)))
            return 0

        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
        backup = args.env_file.with_name(f"{args.env_file.name}.plan067c.bak.{stamp}")
        shutil.copy2(args.env_file, backup)
        os.chmod(backup, 0o600)
        for key, value in desired.items():
            replace_or_append(lines, key, value)
        atomic_write(args.env_file, "".join(lines))
        print(f"APPLIED: {args.env_file} (backup={backup})")
        print("UPDATED_KEYS: " + ", ".join(sorted(desired)))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

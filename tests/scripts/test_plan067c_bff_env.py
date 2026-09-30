from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "inject-plan-067c-bff-env.py"


def run_injector(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_apply_injects_bff_keys_without_printing_secret(tmp_path: Path) -> None:
    target = tmp_path / "office.env"
    target.write_text("QYUNSLATION_ENV=production\n", encoding="utf-8")
    target.chmod(0o600)
    idp_env = tmp_path / "authentik.env"
    idp_env.write_text(
        "QYUNSLATION_OIDC_CLIENT_ID=qyunslation\n"
        "QYUNSLATION_OIDC_CLIENT_SECRET=unit-test-client-secret\n",
        encoding="utf-8",
    )
    idp_env.chmod(0o600)

    result = run_injector(
        "--env-file",
        str(target),
        "--authentik-env",
        str(idp_env),
        "--apply",
        "--skip-dns",
    )

    assert result.returncode == 0, result.stderr
    assert "unit-test-client-secret" not in result.stdout + result.stderr
    values = dict(
        line.split("=", 1)
        for line in target.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )
    assert values["QYUNSLATION_OIDC_CLIENT_ID"] == "qyunslation"
    assert values["QYUNSLATION_OIDC_CLIENT_SECRET"] == "unit-test-client-secret"
    assert values["QYUNSLATION_OIDC_REDIRECT_URI"] == "https://translate.qyunsgen.com/auth/callback"
    assert values["QYUNSLATION_SESSION_KEY"]
    assert target.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.glob("office.env.plan067c.bak.*"))


def test_existing_session_key_is_not_rotated(tmp_path: Path) -> None:
    target = tmp_path / "office.env"
    target.write_text("QYUNSLATION_SESSION_KEY=keep-me\n", encoding="utf-8")
    target.chmod(0o600)
    idp_env = tmp_path / "authentik.env"
    idp_env.write_text(
        "QYUNSLATION_OIDC_CLIENT_ID=qyunslation\n"
        "QYUNSLATION_OIDC_CLIENT_SECRET=unit-test-client-secret\n",
        encoding="utf-8",
    )
    idp_env.chmod(0o600)

    result = run_injector(
        "--env-file",
        str(target),
        "--authentik-env",
        str(idp_env),
        "--apply",
        "--skip-dns",
    )

    assert result.returncode == 0, result.stderr
    assert "QYUNSLATION_SESSION_KEY=keep-me" in target.read_text(encoding="utf-8")

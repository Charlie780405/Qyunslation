#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-075b：部署前/后门禁（迁移版本、前端构建新鲜度、API 路由探测）。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"
STATIC_INDEX = ROOT / "qyunslation" / "static" / "app" / "index.html"
STATIC_APP = ROOT / "qyunslation" / "static" / "app"

# Routes that must exist after PLAN-074; 401/403 = registered, 404 = stale backend.
PLAN074_PROBE_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/api/v1/translation-runs/probe-run-id/affiliation-segments"),
    ("POST", "/api/v1/translation-runs/probe-run-id/apply-corrections"),
)


def git_head(root: Path | None = None) -> str | None:
    base = root or ROOT
    try:
        out = subprocess.check_output(
            ["git", "-C", str(base), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def alembic_heads(root: Path | None = None) -> list[str]:
    base = root or ROOT
    try:
        out = subprocess.check_output(
            [sys.executable, "-m", "alembic", "heads"],
            cwd=str(base),
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"alembic heads failed: {exc.output}") from exc
    heads: list[str] = []
    for line in out.splitlines():
        token = line.split()[0].strip() if line.strip() else ""
        if token and token not in heads:
            heads.append(token)
    return heads


def alembic_current(root: Path | None = None) -> str | None:
    base = root or ROOT
    env = os.environ.copy()
    if not env.get("QYUNSLATION_DATABASE_URL"):
        return None
    try:
        out = subprocess.check_output(
            [sys.executable, "-m", "alembic", "current"],
            cwd=str(base),
            env=env,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"alembic current failed: {exc.output}") from exc
    for line in out.splitlines():
        token = line.split()[0].strip() if line.strip() else ""
        if token and not token.startswith("INFO"):
            return token
    return None


def check_migration_aligned(root: Path | None = None) -> tuple[bool, str, dict[str, str | list[str] | None]]:
    base = root or ROOT
    heads = alembic_heads(base)
    if not heads:
        return False, "no alembic heads found", {"heads": [], "current": None}
    if len(heads) > 1:
        return False, f"multiple alembic heads: {heads}", {"heads": heads, "current": None}
    current = alembic_current(base)
    if current is None:
        return False, "QYUNSLATION_DATABASE_URL unset or alembic current empty", {
            "heads": heads,
            "current": None,
        }
    if current != heads[0]:
        return (
            False,
            f"database revision {current} != code head {heads[0]}; run alembic upgrade head after backup",
            {"heads": heads, "current": current},
        )
    return True, "migration aligned", {"heads": heads, "current": current}


def _newest_source_mtime(root: Path | None = None) -> float | None:
    base = FRONTEND_SRC if root is None else root
    if not base.is_dir():
        return None
    newest = 0.0
    found = False
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".vue", ".js", ".ts", ".css"}:
            continue
        found = True
        newest = max(newest, path.stat().st_mtime)
    return newest if found else None


def static_app_dirty(root: Path | None = None) -> bool:
    base = root or ROOT
    try:
        out = subprocess.check_output(
            ["git", "-C", str(base), "status", "--porcelain", "qyunslation/static/app/"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return bool(out.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_frontend_fresh(root: Path | None = None) -> tuple[bool, str, dict[str, object]]:
    base = root or ROOT
    index = STATIC_INDEX if root is None else base / "qyunslation" / "static" / "app" / "index.html"
    if not index.is_file():
        return False, f"missing built index: {index}", {}
    src_mtime = _newest_source_mtime(base / "frontend" / "src" if root else None)
    index_mtime = index.stat().st_mtime
    dirty = static_app_dirty(base)
    details: dict[str, object] = {
        "index_html": str(index),
        "index_mtime": datetime.fromtimestamp(index_mtime, tz=timezone.utc).isoformat(),
        "static_dirty": dirty,
    }
    if src_mtime is not None:
        details["newest_src_mtime"] = datetime.fromtimestamp(src_mtime, tz=timezone.utc).isoformat()
        if src_mtime > index_mtime + 1:
            return (
                False,
                "frontend/src is newer than qyunslation/static/app; run (cd frontend && npm run build) and commit",
                details,
            )
    if dirty:
        return (
            False,
            "qyunslation/static/app has uncommitted changes; commit build artifacts before deploy",
            details,
        )
    return True, "frontend build fresh", details


def probe_http(base_url: str, method: str, path: str, timeout: float = 5.0) -> int:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError as exc:
        raise RuntimeError(f"probe failed for {url}: {exc}") from exc


def check_api_routes(
    base_url: str,
    routes: tuple[tuple[str, str], ...] | None = None,
) -> tuple[bool, str, list[dict[str, object]]]:
    probes = routes or PLAN074_PROBE_ROUTES
    rows: list[dict[str, object]] = []
    for method, path in probes:
        status = probe_http(base_url, method, path)
        ok = status in {401, 403, 405, 422}
        rows.append({"method": method, "path": path, "status": status, "ok": ok})
    bad = [r for r in rows if not r["ok"]]
    if bad:
        return (
            False,
            f"stale backend: {len(bad)} route(s) returned unexpected status (expected 401/403/405, not 404)",
            rows,
        )
    return True, "api routes registered", rows


def build_deploy_report(
    *,
    base_url: str,
    root: Path | None = None,
    skip_migration: bool = False,
    skip_frontend: bool = False,
    skip_api: bool = False,
) -> dict[str, object]:
    base = root or ROOT
    report: dict[str, object] = {
        "schema": "plan075-deploy-gate/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_head(base),
        "checks": {},
        "ok": True,
    }
    checks = report["checks"]
    if not skip_migration:
        ok, msg, detail = check_migration_aligned(base)
        checks["migration"] = {"ok": ok, "message": msg, **detail}
        if not ok:
            report["ok"] = False
    if not skip_frontend:
        ok, msg, detail = check_frontend_fresh(base)
        checks["frontend"] = {"ok": ok, "message": msg, **detail}
        if not ok:
            report["ok"] = False
    if not skip_api:
        ok, msg, rows = check_api_routes(base_url)
        checks["api_routes"] = {"ok": ok, "message": msg, "probes": rows}
        if not ok:
            report["ok"] = False
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=("pre", "post", "report"),
        help="pre=before restart, post=after restart, report=all checks",
    )
    parser.add_argument("--base-url", default=os.environ.get("QYUNSLATION_OFFICE_URL", "http://127.0.0.1:8010"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skip-migration", action="store_true")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-api", action="store_true")
    args = parser.parse_args(argv)

    skip_migration = args.skip_migration or args.phase == "post"
    skip_frontend = args.skip_frontend or args.phase == "post"
    skip_api = args.skip_api or args.phase == "pre"

    report = build_deploy_report(
        base_url=args.base_url,
        skip_migration=skip_migration,
        skip_frontend=skip_frontend,
        skip_api=skip_api,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"git commit: {report.get('git_commit')}")
        for name, check in (report.get("checks") or {}).items():
            status = "PASS" if check.get("ok") else "FAIL"
            print(f"{status}: {name} — {check.get('message')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

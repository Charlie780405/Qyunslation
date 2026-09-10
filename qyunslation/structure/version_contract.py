# SPDX-License-Identifier: MPL-2.0
"""PLAN-030ic：加载 versions-030.lock 并解析已安装包版本。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCK_PATH = _REPO_ROOT / "docs" / "contracts" / "versions-030.lock"
_DEFAULT_PDF2ZH_SITE = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
)


def repo_root() -> Path:
    override = os.environ.get("QYUNSLATION_REPO_ROOT", "").strip()
    return Path(override) if override else _REPO_ROOT


def lock_path() -> Path:
    override = os.environ.get("QYUNSLATION_VERSIONS_LOCK", "").strip()
    return Path(override) if override else repo_root() / "docs" / "contracts" / "versions-030.lock"


def pdf2zh_site_packages() -> Path:
    override = os.environ.get("QYUNSLATION_PDF2ZH_SITE", "").strip()
    return Path(override) if override else _DEFAULT_PDF2ZH_SITE


@lru_cache(maxsize=1)
def load_contract() -> dict:
    payload = json.loads(lock_path().read_text(encoding="utf-8"))
    if payload.get("schema") != "versions-030/v1":
        raise ValueError(f"VERSION_LOCK_SCHEMA_UNSUPPORTED: {payload.get('schema')}")
    return payload


def parse_semver(value: str) -> tuple[int, int, int]:
    parts = value.strip().split(".")
    nums: list[int] = []
    for part in parts[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits or "0"))
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


def version_gte(actual: str, minimum: str) -> bool:
    if not actual:
        return False
    return parse_semver(actual) >= parse_semver(minimum)


def _version_in_site(dist_name: str, site: Path) -> str:
    code = (
        "import importlib.metadata as m, sys; "
        f"sys.path.insert(0, {str(site)!r}); "
        f"print(m.version({dist_name!r}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return proc.stdout.strip()
    return ""


def package_version(dist_name: str, *, context: str) -> str:
    if context == "pdf2zh":
        found = _version_in_site(dist_name, pdf2zh_site_packages())
        if found:
            return found
    try:
        return version(dist_name)
    except PackageNotFoundError:
        return ""


def check_locked_packages(
    *,
    context: str | None = None,
) -> list[tuple[str, bool, str, dict[str, str]]]:
    """Return (name, ok, reason, versions) for each locked package."""
    contract = load_contract()
    results: list[tuple[str, bool, str, dict[str, str]]] = []
    for name, spec in contract.get("packages", {}).items():
        if context is not None and str(spec.get("context") or "qyunslation") != context:
            continue
        dist = str(spec.get("distribution") or name)
        ctx = str(spec.get("context") or "qyunslation")
        minimum = str(spec.get("min_version") or "0.0.0")
        actual = package_version(dist, context=ctx)
        versions = {"installed": actual or "missing", "minimum": minimum, "context": ctx}
        if not actual:
            results.append((name, False, f"{dist} not installed in {ctx}", versions))
        elif not version_gte(actual, minimum):
            results.append(
                (name, False, f"{dist} {actual} < {minimum}", versions),
            )
        else:
            results.append((name, True, "ok", versions))
    return results

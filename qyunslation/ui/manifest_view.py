# SPDX-License-Identifier: MPL-2.0
"""PLAN-050c：Manifest → UI 摘要。缺字段 / 截断 fail-closed，禁止把未知显示成 0。"""
from __future__ import annotations

import json
from typing import Any


class ManifestViewError(ValueError):
    """UI 不得猜测计数时抛出。"""


_UNKNOWN = "unknown"
_STATUS_OK = "ok"


def _major(version: str) -> int | None:
    parts = str(version or "").split(".")
    if not parts or not parts[0].isdigit():
        return None
    return int(parts[0])


def _count_or_unknown(value: Any, *, truncated: bool) -> int | str:
    if truncated:
        return _UNKNOWN
    if value is None:
        return _UNKNOWN
    try:
        n = int(value)
    except (TypeError, ValueError):
        return _UNKNOWN
    if n < 0:
        return _UNKNOWN
    return n


def summarize_for_ui(payload: dict[str, Any] | str | None) -> dict[str, Any]:
    """给预扫描卡 / 检查器的稳定摘要。

    - schema major ≠ 1 → 抛 ManifestViewError
    - truncated / blocked / missing summary → 计数为 ``unknown``，不是 0
    """
    if payload is None:
        raise ManifestViewError("MANIFEST_MISSING")
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ManifestViewError("MANIFEST_INVALID_JSON") from exc
    else:
        data = payload
    if not isinstance(data, dict):
        raise ManifestViewError("MANIFEST_NOT_OBJECT")

    version = str(data.get("schema_version") or "")
    major = _major(version)
    if major is None or major != 1:
        raise ManifestViewError("MANIFEST_VERSION_UNSUPPORTED")

    issues = data.get("issues") if isinstance(data.get("issues"), list) else []
    codes = {str(i.get("code") or "") for i in issues if isinstance(i, dict)}
    truncated = any(
        c.endswith("TRUNCATED") or c == "TRUNCATED" or "TRUNCATED" in c for c in codes
    )
    blocked = any("BLOCKED" in c or c.endswith("BLOCKED") for c in codes)
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else None
    if summary is None:
        raise ManifestViewError("MANIFEST_SUMMARY_MISSING")

    figures = _count_or_unknown(summary.get("figure_count"), truncated=truncated)
    tables = _count_or_unknown(summary.get("table_count"), truncated=truncated)
    pages = data.get("canvases")
    page_count: int | str
    if not isinstance(pages, list):
        page_count = _UNKNOWN
    else:
        page_count = len(pages)

    refs_protected = 0
    objects = data.get("objects") if isinstance(data.get("objects"), list) else []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        policy = str(obj.get("translation_policy") or "")
        otype = str(obj.get("type") or "")
        if policy == "PRESERVE" and otype in {"BODY", "CAPTION"}:
            refs_protected += 1

    status = _STATUS_OK
    if blocked:
        status = "blocked"
    elif truncated:
        status = "truncated"

    return {
        "schema_version": version,
        "status": status,
        "page_count": page_count,
        "figure_count": figures,
        "table_count": tables,
        "image_count": _count_or_unknown(
            (summary.get("object_counts") or {}).get("IMAGE")
            if isinstance(summary.get("object_counts"), dict)
            else None,
            truncated=truncated,
        ),
        "refs_protected": refs_protected,
        "issue_count": len(issues),
        "display": {
            "figures": "—" if figures == _UNKNOWN else str(figures),
            "tables": "—" if tables == _UNKNOWN else str(tables),
            "pages": "—" if page_count == _UNKNOWN else str(page_count),
        },
    }


def render_prescan_card(manifest_json: str, *, fallback: str) -> str:
    try:
        card = summarize_for_ui(manifest_json)
    except ManifestViewError as exc:
        return f"{fallback}\n\n结构清单不可用（{exc}），未用 0 填充计数。"
    disp = card["display"]
    status = card["status"]
    warn = ""
    if status != _STATUS_OK:
        warn = f"\n状态：**{status}**（计数可能不完整，未记为 0）"
    return (
        f"{fallback}\n\n"
        f"**结构摘要** 页 {disp['pages']} · Figure {disp['figures']} · "
        f"Table {disp['tables']}{warn}"
    )

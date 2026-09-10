# SPDX-License-Identifier: MPL-2.0
"""PLAN-037 P1-A：表格执行保真信号的可观测摘要（扫描 + 执行）。"""
from __future__ import annotations

from typing import Any

from .models import DocumentStructureManifest, ExecutionStatus, ObjectType

SCAN_CODES = frozenset({"TABLE_CONTINUATION_UNLINKED"})
EXEC_REASON_CODES = frozenset({"table_digit_drift", "table_translate_failed", "table_writeback_failed"})


def table_fidelity_payload(manifest: DocumentStructureManifest | None) -> dict[str, Any]:
    if manifest is None:
        return {"scan": [], "execution": [], "summary_text": ""}
    scan_rows = _scan_rows(manifest)
    execution_rows = _execution_rows(manifest)
    parts: list[str] = []
    for row in scan_rows:
        parts.append(row["message"])
    for row in execution_rows:
        parts.append(row["message"])
    return {
        "scan": scan_rows,
        "execution": execution_rows,
        "summary_text": " ".join(parts).strip(),
    }


def scan_table_fidelity_hint(manifest: DocumentStructureManifest | None) -> str:
    rows = _scan_rows(manifest)
    if not rows:
        return ""
    return " ".join(row["message"] for row in rows)


def execution_table_fidelity_hint(manifest: DocumentStructureManifest | None) -> str:
    rows = _execution_rows(manifest)
    if not rows:
        return ""
    return " ".join(row["message"] for row in rows)


def append_table_fidelity_hint(base: str, manifest: DocumentStructureManifest | None) -> str:
    hint = scan_table_fidelity_hint(manifest)
    if not hint:
        return base
    text = (base or "").rstrip("。")
    return f"{text} {hint}。"


def _scan_rows(manifest: DocumentStructureManifest) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for issue in manifest.issues or []:
        if issue.code not in SCAN_CODES:
            continue
        details = dict(issue.details or {})
        if issue.code == "TABLE_CONTINUATION_UNLINKED":
            page = details.get("page")
            table = details.get("table")
            message = (
                f"⚠ TABLE_CONTINUATION_UNLINKED：第 {page} 页续表 {table} 有题注但未链接网格"
                if page is not None and table is not None
                else f"⚠ TABLE_CONTINUATION_UNLINKED：{issue.message}"
            )
        else:
            message = f"⚠ {issue.code}：{issue.message}"
        rows.append(
            {
                "code": issue.code,
                "severity": str(issue.severity),
                "message": message,
                "details": details,
            }
        )
    return rows


def _execution_rows(manifest: DocumentStructureManifest) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for obj in manifest.objects or []:
        if obj.type is not ObjectType.TABLE:
            continue
        semantic_id = obj.semantic_id or obj.object_id
        checks = (obj.output_evidence.checks if obj.output_evidence else {}) or {}
        status = obj.execution_status
        if status is ExecutionStatus.TRANSLATED and checks.get("digits_preserved") is True:
            rows.append(
                {
                    "code": "digits_preserved",
                    "semantic_id": semantic_id,
                    "message": f"✓ {semantic_id}：digits_preserved",
                }
            )
            continue
        reason = (obj.reason_code or "").lower()
        error_text = str(checks.get("error") or "")
        if "TABLE_DIGIT_DRIFT" in error_text or reason == "table_digit_drift":
            rows.append(
                {
                    "code": "TABLE_DIGIT_DRIFT",
                    "semantic_id": semantic_id,
                    "message": f"✗ {semantic_id}：TABLE_DIGIT_DRIFT",
                }
            )
            continue
        if reason in EXEC_REASON_CODES and status in {
            ExecutionStatus.FAILED_HARD,
            ExecutionStatus.FAILED_SOFT,
        }:
            code = reason.upper()
            rows.append(
                {
                    "code": code,
                    "semantic_id": semantic_id,
                    "message": f"✗ {semantic_id}：{code}",
                }
            )
    return rows

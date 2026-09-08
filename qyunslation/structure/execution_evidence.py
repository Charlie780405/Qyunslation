# SPDX-License-Identifier: MPL-2.0
"""Shared helpers for manifest execution audit fields."""
from __future__ import annotations

from .models import ExecutionStatus, OutputEvidence, SemanticObject


def write_output_evidence(
    obj: SemanticObject,
    *,
    status: ExecutionStatus,
    reason_code: str | None = None,
    asset_ids: list[str] | None = None,
    checks: dict | None = None,
) -> None:
    obj.execution_status = status
    if reason_code:
        obj.reason_code = reason_code
    payload = dict(checks or {})
    if asset_ids:
        obj.output_evidence = OutputEvidence(asset_ids=list(asset_ids), checks=payload)
    elif payload:
        obj.output_evidence = OutputEvidence(checks=payload)
    elif status in {
        ExecutionStatus.TRANSLATED,
        ExecutionStatus.EXPLICITLY_SKIPPED,
        ExecutionStatus.FAILED_SOFT,
        ExecutionStatus.FAILED_HARD,
    }:
        obj.output_evidence = OutputEvidence(checks=payload)

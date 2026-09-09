# SPDX-License-Identifier: MPL-2.0
"""Shared helpers for manifest execution audit fields."""
from __future__ import annotations

from .models import ExecutionStatus, ObjectType, OutputEvidence, SemanticObject

_KEEP_ON_MERGE = {ObjectType.FIGURE, ObjectType.IMAGE, ObjectType.TABLE}


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


def merge_prior_execution(manifest, *, keep_types: set[ObjectType] | None = None) -> None:
    """后处理分阶段回写时，保留另一阶段已落地的终态。"""
    from .manifest_store import ManifestStore

    keep = keep_types or _KEEP_ON_MERGE
    try:
        prior = ManifestStore().get_execution(manifest.document.source_sha256)
    except Exception:
        return
    if prior is None:
        return
    by_id = {obj.semantic_id: obj for obj in prior.objects}
    for obj in manifest.objects:
        prev = by_id.get(obj.semantic_id)
        if prev is None or obj.type not in keep:
            continue
        if (
            obj.execution_status is ExecutionStatus.PENDING
            and prev.execution_status is not ExecutionStatus.PENDING
        ):
            obj.execution_status = prev.execution_status
            obj.reason_code = prev.reason_code
            obj.output_evidence = prev.output_evidence

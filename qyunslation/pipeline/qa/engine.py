# SPDX-License-Identifier: MPL-2.0
"""PLAN-071e：TranslationRun 确定性 QA 引擎（最小六类）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QaFinding:
    category: str
    severity: str  # blocker | warning | info
    code: str
    message: str
    object_id: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def run_deterministic_qa(
    *,
    manifest: dict[str, Any] | None = None,
    term_summary: dict[str, Any] | None = None,
    settings_snapshot: dict[str, Any] | None = None,
    translated_text_sample: str | None = None,
    source_page_count: int | None = None,
    output_page_count: int | None = None,
    logo_present: bool | None = None,
) -> list[QaFinding]:
    findings: list[QaFinding] = []
    manifest = manifest or {}
    term_summary = term_summary or {}
    settings_snapshot = settings_snapshot or {}

    # 1) Integrity
    if translated_text_sample is not None and not translated_text_sample.strip():
        findings.append(
            QaFinding(
                category="integrity",
                severity="blocker",
                code="EMPTY_TRANSLATION",
                message="译文为空",
            )
        )
    if translated_text_sample and "Fallback to simple translation" in translated_text_sample:
        findings.append(
            QaFinding(
                category="integrity",
                severity="warning",
                code="FALLBACK_PRESENT",
                message="存在 fallback 段落，需人工确认",
            )
        )

    # 2) Clinical / regulatory literals
    sample = translated_text_sample or ""
    if "^{th}" in sample or "^{st}" in sample:
        findings.append(
            QaFinding(
                category="clinical",
                severity="blocker",
                code="ORDINAL_ARTIFACT",
                message="出现序数上标伪影",
            )
        )

    # 3) Terminology
    if term_summary.get("status") == "snapshot_pending":
        findings.append(
            QaFinding(
                category="terminology",
                severity="warning",
                code="TERM_SNAPSHOT_PENDING",
                message="术语快照尚未完成",
            )
        )
    conflicts = term_summary.get("high_risk_conflicts") or []
    for item in conflicts:
        findings.append(
            QaFinding(
                category="terminology",
                severity="blocker",
                code="TERM_HIGH_RISK_CONFLICT",
                message=str(item.get("message") or "高风险术语冲突"),
                evidence=item if isinstance(item, dict) else {"raw": item},
            )
        )

    # 4) Structure
    objects = manifest.get("objects") or []
    if manifest and not objects:
        findings.append(
            QaFinding(
                category="structure",
                severity="blocker",
                code="MANIFEST_EMPTY_OBJECTS",
                message="Manifest 无对象",
            )
        )

    # 5) Layout / preserve
    if logo_present is False:
        findings.append(
            QaFinding(
                category="layout",
                severity="blocker",
                code="LOGO_MISSING",
                message="期望的 Logo/机构标识缺失",
            )
        )
    if (
        source_page_count is not None
        and output_page_count is not None
        and source_page_count != output_page_count
    ):
        findings.append(
            QaFinding(
                category="layout",
                severity="blocker",
                code="PAGE_COUNT_MISMATCH",
                message=f"页数不一致 source={source_page_count} output={output_page_count}",
            )
        )

    # 6) Artifact consistency
    expected_gen = settings_snapshot.get("generation")
    manifest_gen = (manifest.get("extensions") or {}).get("generation")
    if expected_gen is not None and manifest_gen is not None and expected_gen != manifest_gen:
        findings.append(
            QaFinding(
                category="consistency",
                severity="blocker",
                code="GENERATION_MISMATCH",
                message="Manifest generation 与任务不一致",
            )
        )

    return findings


def summarize(findings: list[QaFinding]) -> dict[str, int]:
    summary = {"blocker": 0, "warning": 0, "info": 0}
    for item in findings:
        if item.severity in summary:
            summary[item.severity] += 1
    return summary


def quality_state_from_findings(findings: list[QaFinding]) -> str:
    if any(item.severity == "blocker" for item in findings):
        return "qa_blocked"
    return "review_ready"

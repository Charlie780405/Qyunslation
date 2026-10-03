"""PLAN-076i: AD QA inspection for PDF and non-PDF outputs."""
from __future__ import annotations

import os
from typing import Any

from qyunslation.pipeline.ad_prompt import detect_domain_evidence
from qyunslation.pipeline.ad_qa import QaContext, run_ad_deterministic_qa
from qyunslation.pipeline.ad_semantic import orchestrate_ad_semantic_qa
from qyunslation.pipeline.ad_termbase import build_ad_term_policy
from qyunslation.pipeline.qa.engine import QaFinding


def _direction_from_run(direction: str) -> str:
    return "en-zh" if direction == "English → 简体中文" else "zh-en"


def inspect_ad_text_pair(
    *,
    source_text: str,
    target_text: str,
    direction_label: str,
    settings_snapshot: dict[str, Any] | None,
) -> tuple[list[QaFinding], dict[str, Any], bool]:
    findings: list[QaFinding] = []
    direction = _direction_from_run(direction_label)
    if not source_text.strip() or not target_text.strip():
        findings.append(
            QaFinding(
                category="ad",
                severity="blocker",
                code="AD_QA_SOURCE_UNAVAILABLE",
                message="无法抽取源文或译文文本以执行 AD QA",
            )
        )
        return findings, {"status": "unavailable"}, False

    ad_policy = build_ad_term_policy(source_text, direction)
    findings.extend(
        run_ad_deterministic_qa(
            QaContext(
                source=source_text,
                target=target_text,
                direction=direction,
                terms=ad_policy.get("terms") or {},
                aliases=ad_policy.get("aliases") or {},
            )
        )
    )
    if not detect_domain_evidence(source_text):
        findings.append(
            QaFinding(
                category="ad",
                severity="blocker",
                code="AD_DOMAIN_EVIDENCE_MISSING",
                message="源文缺少可验证的 AD 领域锚点",
            )
        )

    snapshot: dict[str, Any] = {
        "status": "ready",
        "schema": "076-ad-termbase-v1",
        "direction": direction,
        "termbase_version": ad_policy.get("termbase_version"),
        "terms": ad_policy.get("metadata") or [],
    }
    settings = dict(settings_snapshot or {})
    semantic_mode = str(settings.get("semantic_qa_mode") or "shadow").casefold()
    reviewer_url = (os.environ.get("QYUNSLATION_AD_SEMANTIC_REVIEWER_URL") or "").strip() or None

    def _repair_fn(source: str, current_target: str, issues: list) -> str:
        return current_target

    semantic = orchestrate_ad_semantic_qa(
        source=source_text,
        target=target_text,
        mode=semantic_mode,
        reviewer_url=reviewer_url,
        repair_fn=_repair_fn if semantic_mode == "required" else None,
    )
    snapshot["semantic_qa"] = semantic
    semantic_degraded = bool(semantic.get("degraded"))
    if semantic.get("fact_drift"):
        findings.append(
            QaFinding(
                category="ad_semantic",
                severity="blocker",
                code="AD_REPAIR_FACT_DRIFT",
                message="语义修复改变了受保护事实",
                evidence={"repair_attempts": semantic.get("repair_attempts")},
            )
        )
    elif semantic_mode == "required" and semantic_degraded:
        findings.append(
            QaFinding(
                category="ad_semantic",
                severity="warning",
                code="AD_QA_DEGRADED",
                message="AD 语义 QA 不可用或超时",
                evidence={"semantic_qa": semantic},
            )
        )
    elif semantic_mode == "required" and semantic.get("repaired"):
        repaired_target = str(semantic.get("target") or target_text)
        findings = [
            item
            for item in findings
            if item.code not in {"AD_NUMBER_DRIFT", "AD_TERM_MISSING", "AD_NEGATION_DRIFT", "AD_MODALITY_DRIFT"}
        ]
        findings.extend(
            run_ad_deterministic_qa(
                QaContext(
                    source=source_text,
                    target=repaired_target,
                    direction=direction,
                    terms=ad_policy.get("terms") or {},
                    aliases=ad_policy.get("aliases") or {},
                )
            )
        )
        snapshot["semantic_qa"]["post_repair_rerun"] = True
    return findings, snapshot, semantic_degraded

# SPDX-License-Identifier: MPL-2.0
"""PLAN-034f：句段流水线 translate → QA → (review) → (repair) → 再检。"""
from __future__ import annotations

from typing import Any

from qyunslation.gateway.qa import QaResult, run_deterministic_qa
from qyunslation.gateway.risk import grade_risk


def run_segment_pipeline(
    source: str,
    *,
    target: str | None = None,
    role: str | None = "body",
    domain: str | None = "",
    forbidden: list[str] | None = None,
    table_qc_codes: list[str] | None = None,
    page_qc_codes: list[str] | None = None,
    provider: Any | None = None,
    enable_review: bool = False,
    enable_repair: bool = True,
) -> dict[str, Any]:
    """对单段执行 QA；critical 时可选用 provider.repair 一轮后再检。

    默认不调用 translate（调用方已有机译）；若 ``target`` 为空且有 provider，则先 translate。
    """
    risk = grade_risk(domain, role)
    review_text: str | None = None
    repaired_text: str | None = None
    working = target

    if risk.get("policy") == "PRESERVE":
        qa = run_deterministic_qa(
            source,
            working or source,
            role=role,
            domain=domain,
            forbidden=forbidden,
            table_qc_codes=table_qc_codes,
            page_qc_codes=page_qc_codes,
        )
        return {
            "target": working or source,
            "repaired_text": None,
            "review": None,
            "qa": qa.to_dict(),
            "risk": risk,
            "repaired": False,
        }

    if (working is None or not str(working).strip()) and provider is not None:
        working = provider.translate(source)

    qa = run_deterministic_qa(
        source,
        working or "",
        role=role,
        domain=domain,
        forbidden=forbidden,
        table_qc_codes=table_qc_codes,
        page_qc_codes=page_qc_codes,
    )

    if enable_review and provider is not None:
        findings = [f.message for f in qa.findings]
        review_text = provider.review(source, working or "", findings=findings)

    repaired = False
    if enable_repair and qa.blocked and provider is not None:
        findings = [f"{f.check}: {f.message}" for f in qa.findings if f.severity == "critical"]
        repaired_text = provider.repair(source, working or "", findings=findings)
        working = repaired_text
        repaired = True
        qa = run_deterministic_qa(
            source,
            working or "",
            role=role,
            domain=domain,
            forbidden=forbidden,
            table_qc_codes=table_qc_codes,
            page_qc_codes=page_qc_codes,
        )

    return {
        "target": working,
        "repaired_text": repaired_text,
        "review": review_text,
        "qa": qa.to_dict(),
        "risk": risk,
        "repaired": repaired,
    }

# SPDX-License-Identifier: MPL-2.0
"""PLAN-034f：确定性医药 QA 编排（12 项清单）。"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from qyunslation.gateway.risk import grade_risk, normalize_role
from qyunslation.persist.concept_repo import detect_forbidden
from qyunslation.structure.protect import missing_protected_tokens
from qyunslation.structure.text_sanitize import IL_MARKUP_LEAK, has_il_markup_leak

# 清单项 id（验收用）
CHECKLIST = (
    "numbers",
    "doses",
    "units",
    "percentages",
    "dates",
    "negation",
    "abbreviations",
    "terminology",
    "citations",
    "table_relations",
    "omissions",
    "references",
)

_NEG_EN = re.compile(
    r"\b(?:no|not|never|without|neither|nor|non[- ]?|absent|negative)\b",
    re.I,
)
_NEG_ZH = re.compile(r"(?:不|无|未|非|没有|并非|阴性)")
_UNIT_RE = re.compile(r"\b(?:mg|kg|ml|mm|cm|µg|ug|ng|IU)\b", re.I)
_PCT_RE = re.compile(r"\b\d+(?:\.\d+)?%")
_DATE_RE = re.compile(r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b")
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_DOSE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|kg|ml|µg|ug|ng|IU)\b",
    re.I,
)
_CITE_RE = re.compile(r"\[\d+(?:[-,]\d+)*\]")
_ABBR_RE = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)?\b")


@dataclass
class Finding:
    check: str
    severity: str  # critical | warning | info
    message: str
    detail: str | None = None


@dataclass
class QaResult:
    findings: list[Finding] = field(default_factory=list)
    blocked: bool = False
    risk: dict[str, Any] = field(default_factory=dict)
    checklist_covered: list[str] = field(default_factory=lambda: list(CHECKLIST))

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [asdict(f) for f in self.findings],
            "blocked": self.blocked,
            "risk": self.risk,
            "checklist_covered": self.checklist_covered,
        }


def _tokens_of(pattern: re.Pattern[str], text: str) -> list[str]:
    return pattern.findall(text or "")


def _missing_tokens(source_tokens: Sequence[str], target: str) -> list[str]:
    missing = []
    tgt = target or ""
    for tok in source_tokens:
        if tok and tok not in tgt:
            missing.append(tok)
    return missing


def run_deterministic_qa(
    source: str,
    target: str,
    *,
    role: str | None = "body",
    domain: str | None = "",
    forbidden: list[str] | None = None,
    table_qc_codes: list[str] | None = None,
    page_qc_codes: list[str] | None = None,
) -> QaResult:
    """对单段源/译文跑 12 项确定性检查。"""
    risk = grade_risk(domain, role)
    result = QaResult(risk=risk)
    role_n = normalize_role(role)
    src = source or ""
    tgt = target or ""

    # references：PRESERVE — 译文应为空或与源相同；进入 LLM 内容视为 critical
    if risk.get("policy") == "PRESERVE" or role_n == "references":
        if tgt.strip() and tgt.strip() != src.strip():
            result.findings.append(
                Finding(
                    check="references",
                    severity="critical",
                    message="references altered; must PRESERVE",
                )
            )
        # 其余检查对 PRESERVE 区跳过语义项
        result.blocked = any(f.severity == "critical" for f in result.findings)
        return result

    # omissions：空译文
    if src.strip() and not tgt.strip():
        result.findings.append(
            Finding(check="omissions", severity="critical", message="empty translation")
        )

    # protect-based：数字/剂量/单位/百分比/日期/引用/缩写
    missing = missing_protected_tokens(src, tgt)
    if missing:
        for tok in missing:
            check = "numbers"
            sev = "critical"
            if _DOSE_RE.fullmatch(tok or ""):
                check = "doses"
            elif _UNIT_RE.fullmatch(tok or ""):
                check = "units"
            elif _PCT_RE.fullmatch(tok or ""):
                check = "percentages"
            elif _DATE_RE.fullmatch(tok or ""):
                check = "dates"
            elif _CITE_RE.fullmatch(tok or ""):
                check = "citations"
            elif _ABBR_RE.fullmatch(tok or ""):
                check = "abbreviations"
                sev = "warning"
            result.findings.append(
                Finding(
                    check=check,
                    severity=sev,
                    message=f"protected token missing: {tok}",
                    detail=tok,
                )
            )

    # 显式剂量/百分比/日期交叉（protect 漏网时）
    for check, pattern in (
        ("doses", _DOSE_RE),
        ("percentages", _PCT_RE),
        ("dates", _DATE_RE),
        ("citations", _CITE_RE),
    ):
        miss = _missing_tokens(_tokens_of(pattern, src), tgt)
        for tok in miss:
            if any(f.detail == tok for f in result.findings):
                continue
            result.findings.append(
                Finding(
                    check=check,
                    severity="critical",
                    message=f"{check} token missing: {tok}",
                    detail=tok,
                )
            )

    # units：源有单位、译文丢失
    for tok in _tokens_of(_UNIT_RE, src):
        if tok not in tgt and not any(f.detail == tok for f in result.findings):
            result.findings.append(
                Finding(
                    check="units",
                    severity="critical",
                    message=f"unit missing: {tok}",
                    detail=tok,
                )
            )

    # numbers：裸数字丢失（非单位附着时 protect 已覆盖部分）
    src_nums = set(_tokens_of(_NUM_RE, src))
    tgt_nums = set(_tokens_of(_NUM_RE, tgt))
    for n in sorted(src_nums - tgt_nums):
        if any(f.detail == n for f in result.findings):
            continue
        # 跳过已作为剂量一部分报告的
        result.findings.append(
            Finding(
                check="numbers",
                severity="critical",
                message=f"number missing: {n}",
                detail=n,
            )
        )

    # negation：源有否定、译文否定极性丢失（启发式）
    src_neg = bool(_NEG_EN.search(src) or _NEG_ZH.search(src))
    tgt_neg = bool(_NEG_EN.search(tgt) or _NEG_ZH.search(tgt))
    if src_neg and tgt.strip() and not tgt_neg:
        result.findings.append(
            Finding(
                check="negation",
                severity="critical",
                message="negation present in source but absent in target",
            )
        )

    # abbreviations：源大写缩写丢失（warning；protect 已部分覆盖）
    for abbr in _tokens_of(_ABBR_RE, src):
        if abbr not in tgt and not any(f.detail == abbr for f in result.findings):
            result.findings.append(
                Finding(
                    check="abbreviations",
                    severity="warning",
                    message=f"abbreviation missing: {abbr}",
                    detail=abbr,
                )
            )

    # terminology：禁用译法
    if forbidden and detect_forbidden(tgt, forbidden):
        result.findings.append(
            Finding(
                check="terminology",
                severity="critical",
                message="forbidden terminology hit",
            )
        )

    # table_relations：wrap 外部 QC 码
    hard_table = {
        "LABEL_VALUE_SHIFT",
        "CELL_MERGE",
        "KEY_VALUE_COLLAPSE",
        "SPAN_ORDER_DRIFT",
        "COLUMN_CLUSTER_DRIFT",
    }
    for code in table_qc_codes or []:
        sev = "critical" if code in hard_table else "warning"
        result.findings.append(
            Finding(
                check="table_relations",
                severity=sev,
                message=f"table_qc: {code}",
                detail=code,
            )
        )

    # omissions：页级 QC wrap + IL markup
    for code in page_qc_codes or []:
        result.findings.append(
            Finding(
                check="omissions",
                severity="warning",
                message=f"page_qc: {code}",
                detail=code,
            )
        )
    if has_il_markup_leak(tgt):
        result.findings.append(
            Finding(
                check="omissions",
                severity="warning",
                message=IL_MARKUP_LEAK,
            )
        )

    # references checklist always marked covered even when N/A for body
    result.blocked = any(f.severity == "critical" for f in result.findings)
    return result


def ensure_checklist_coverage() -> list[str]:
    """供 verify：返回已覆盖的 12 项 id。"""
    return list(CHECKLIST)

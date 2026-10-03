"""PLAN-076e/076i: deterministic, direction-aware AD translation QA.

The checks run on whole documents, so they compare *multisets* of protected
values rather than token order, and they only treat values as protected when
they carry clinical meaning (unit, percent, decimal, range, comparator, count
noun or three or more digits). Bare one- or two-digit integers (figure
numbers, citation markers, "type 2", "H1") are left to semantic QA.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping

from qyunslation.pipeline.qa.engine import QaFinding


@dataclass(frozen=True)
class QaContext:
    source: str
    target: str
    direction: str
    terms: Mapping[str, str] = field(default_factory=dict)
    aliases: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９．", "0123456789.")

# "1:00-4:00" is a clock range, but "2: 33–66%" is a scale level followed by a percentage band.
_CLOCK_PATTERN = r"(?<!\d)(\d{1,2}):([0-5]\d)(?::[0-5]\d)?(?!\d)(?!\s*%)(?![–\-~～]\s*\d{1,3}(?:\.\d+)?\s*%)"

# Identifiers that contain digits but carry no clinical value.
_NOISE_RES = (
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),  # email
    re.compile(r"https?://[^\s\u3000-\u9fff\uff00-\uffef]+|www\.[^\s\u3000-\u9fff\uff00-\uffef]+"),
    re.compile(r"(?<![\d.])10\.\d{4,9}/[^\s\u3000-\u9fff\uff00-\uffef]+"),  # DOI
    re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"),  # ORCID
    re.compile(r"\bISSN\s*[:：]?\s*\d{4}-\d{3}[\dX]\b", re.I),
    re.compile(r"(?<![A-Za-z])(?:CRD|NCT|ChiCTR|PROSPERO|IRCT|UMIN|ISRCTN|EudraCT)[-\s]?\w*\d{4,}\w*(?![A-Za-z0-9])", re.I),
    re.compile(r"(?:\+\d{1,3}-)?\d{2,4}(?:-\d{2,4}){2,}"),  # phone/fax
    re.compile(r"(?<![\d.])\d+(?:\.\d+){2,}(?!\d)"),  # software versions 4.3.1
    re.compile(r"\[\s*\d+(?:\s*[-–,，、]\s*\d+)*\s*\]"),  # citation markers [ 6 , 7 ]
    re.compile(_CLOCK_PATTERN),  # clock time, handled separately
)
_CLOCK_RE = re.compile(_CLOCK_PATTERN)
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9,
    "Sept": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
# "May" is also a modal verb, so it only counts as a month next to a day/year.
_MONTH_RE = re.compile(
    r"\b(" + "|".join(sorted((name for name in _MONTHS if name != "May"), key=len, reverse=True)) + r")\b\.?"
    r"|\b(May)\b(?=,?\s+\d)|(?<=\d\s)(May)\b"
)
_CJK_MONTH_RE = re.compile(r"(?<![\d.])0?(1[0-2]|[1-9])\s*月(?![龄份])")
_CJK_MONTH_RANGE_RE = re.compile(r"(?<![\d.])0?(1[0-2]|[1-9])\s*[-–—~～至]\s*0?(1[0-2]|[1-9])\s*月(?![龄份])")

_SCALE_WORDS = {
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
    "trillion": 1_000_000_000_000,
    "千": 1_000,
    "万": 10_000,
    "百万": 1_000_000,
    "千万": 10_000_000,
    "亿": 100_000_000,
    "千亿": 100_000_000_000,
    "万亿": 1_000_000_000_000,
}
_SCALE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(" + "|".join(sorted(_SCALE_WORDS, key=len, reverse=True)) + r")(?![A-Za-z])",
    re.I,
)
# "200/1850" protects both parts of a fraction; gene names like ERK1/2 are skipped.
_FRACTION_RE = re.compile(r"(?<![A-Za-z\d.])(?=\d{2,}|\d/\d{2,})(\d{1,5})\s*/\s*(\d{1,5})(?![\d.])")

# Units whose canonical form is kept on the value.
_UNIT_CANON = {
    "mg": "mg", "g": "g", "kg": "kg", "μg": "mcg", "µg": "mcg", "mcg": "mcg", "ug": "mcg", "ng": "ng", "pg": "pg",
    "ml": "mL", "l": "L", "dl": "dL", "iu": "IU",
    "mg/kg": "mg/kg", "mg/d": "mg/d", "mg/day": "mg/d", "mg/dl": "mg/dL",
    "ng/ml": "ng/mL", "pg/ml": "pg/mL", "ng/l": "ng/L", "pg/l": "pg/L",
    "cells/μl": "cells/mcL", "cells/µl": "cells/mcL", "cells/mcl": "cells/mcL",
    "毫克": "mg", "克": "g", "千克": "kg", "微克": "mcg", "毫升": "mL",
    "%": "%", "％": "%", "cm": "cm", "mm": "mm", "cm2": "cm2", "cm²": "cm2", "°c": "degC", "℃": "degC",
    "j/cm2": "J/cm2", "j/cm²": "J/cm2", "mj/cm2": "mJ/cm2", "mj/cm²": "mJ/cm2",
}
# Duration/age units are stripped and do not protect bare one- or two-digit
# values: English often omits them ("before 40", "week 16") while Chinese always
# writes 岁/周, so document-level counts would never agree. Durations are
# covered by fact annotations and semantic QA instead.
_BARE_UNITS = {
    "week", "weeks", "wk", "wks", "周", "星期",
    "day", "days", "天",
    "month", "months", "个月", "月龄",
    "year", "years", "yr", "yrs", "岁",
    "hour", "hours", "h", "hr", "hrs", "小时",
    "minute", "minutes", "min", "分钟",
}
_UNIT_PATTERN = "|".join(sorted((re.escape(unit) for unit in {*_UNIT_CANON, *_BARE_UNITS}), key=len, reverse=True))
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9.])"
    r"(?P<cmp>(?:≥|≤|±|>=|<=|≧|≦|⩾|⩽|<|>)\s*)?"
    r"(?P<a>\d+(?:\.\d+)?)"
    r"(?:\s*(?P<dash>[-–—~～至]|to)\s*(?P<b>\d+(?:\.\d+)?))?"
    r"[\s-]*(?P<unit>" + _UNIT_PATTERN + r")?"
    r"(?![A-Za-z0-9])",
    re.I,
)

_NEGATION_EN = re.compile(
    r"\b(?:no|not|without|never|neither|nor|none|cannot|unable|absence of|lack of|lacking|failed to|negative|ineffective|unclear|unknown)\b|n't\b",
    re.I,
)
_NEGATION_ZH = re.compile(
    r"没有|无法|未能|不能|不得|禁止|不应|不可|并非|不是|未见|否认|无效|阴性|不存在|不足|未达|未发现|未观察到|无关|无明显|无显著|不再|不需要|未经|不含|尚无|尚未|均无|并无|无需"
    r"|无一|未从|未住院|未纳入|未排除|未报告|未接受|未进行|未提供|未获得|未使用|未系统|未包括|不包括|未检测|未出现|未发生|无任何|无需要|不良反应为无"
)
_MODALITY = {
    # Deontic markers only; ability ("cannot be obtained") and epistemic
    # hedges are deliberately excluded because they are not translation-stable.
    "prohibition": (
        re.compile(r"\b(?:must not|shall not|should not|may not|prohibited|contraindicated|not permitted|not allowed|not recommended)\b", re.I),
        re.compile(r"不得|禁止|禁用|不应(?!答)|不宜|不可(?![能以逆避])|不允许|不建议|不推荐"),
    ),
    "obligation": (
        re.compile(r"\b(?:must|shall|should|required?|requires|need(?:s|ed)? to|needed|necessary|warranted)\b", re.I),
        re.compile(r"必须|应当|应该|应予|须|需|(?<![反适对效响供感顺特相呼回答报照])应(?![用激答性付对变激])"),
    ),
    "permission": (
        re.compile(r"\b(?:may|might|can|could|permitted to|allowed to)\b", re.I),
        re.compile(r"可以|可能|允许|能够|可(?=[用以在使考将与由作为])"),
    ),
}


_STRONG_OBLIGATION = re.compile(r"\b(?:must|shall)\b|必须|应当", re.I)


def _normalize_numeric_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = value.translate(_FULLWIDTH_DIGITS)
    for pattern in _NOISE_RES:
        value = pattern.sub(" ", value)
    value = re.sub(r"cm\s*[2²](?!\d)", "cm2", value)
    value = re.sub(r"%(?=[A-Za-z])", "% ", value)
    # "SPSS23.0" vs "SPSS version 23.0": detach product names from version/size numbers.
    value = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", value)
    return value


def _format_value(raw: str, scale: int = 1) -> str:
    number = float(raw) * scale
    if number.is_integer():
        return str(int(number))
    return f"{number:.6g}"


def _canonical_unit(unit: str | None) -> tuple[str, bool]:
    """Return (canonical unit suffix, protected) for a matched unit."""
    if not unit:
        return "", False
    lowered = unit.lower()
    if unit in _BARE_UNITS or lowered in _BARE_UNITS:
        return "", False
    return _UNIT_CANON.get(unit) or _UNIT_CANON.get(lowered, ""), True


def _numbers(text: str) -> list[str]:
    """Return protected numeric values as canonical strings (multiset semantics)."""
    found: list[str] = []
    for match in _CLOCK_RE.finditer(unicodedata.normalize("NFKC", text or "")):
        found.append(f"{int(match.group(1))}:{match.group(2)}")
    normalized = _normalize_numeric_text(text)
    for match in _MONTH_RE.finditer(normalized):
        found.append(f"month:{_MONTHS[match.group(1) or match.group(2) or match.group(3)]}")
    for match in _CJK_MONTH_RANGE_RE.finditer(normalized):
        found.append(f"month:{int(match.group(1))}")
    normalized = _CJK_MONTH_RANGE_RE.sub(lambda m: f" {m.group(2)}月", normalized)
    for match in _CJK_MONTH_RE.finditer(normalized):
        found.append(f"month:{int(match.group(1))}")
    normalized = _CJK_MONTH_RE.sub(" ", normalized)
    skip: list[tuple[int, int]] = []
    for match in _SCALE_RE.finditer(normalized):
        found.append(_format_value(match.group(1), _SCALE_WORDS[match.group(2).lower()]))
        skip.append(match.span())
    for match in _FRACTION_RE.finditer(normalized):
        found.append(f"{_format_value(match.group(1))}/{_format_value(match.group(2))}")
        skip.append(match.span())
    for match in _NUMBER_RE.finditer(normalized):
        if any(start <= match.start("a") < end for start, end in skip):
            continue
        canon_unit, unit_protected = _canonical_unit(match.group("unit"))
        values = [match.group("a")] + ([match.group("b")] if match.group("b") else [])
        for value in values:
            if _YEAR_RE.fullmatch(value) and not canon_unit:
                continue
            protected = unit_protected or "." in value or len(value) >= 3
            if not protected:
                continue
            found.append(f"{_format_value(value)}{canon_unit}")
    return found


def _modality_classes(text: str) -> set[str]:
    present: set[str] = set()
    for name, patterns in _MODALITY.items():
        if any(pattern.search(text or "") for pattern in patterns):
            present.add(name)
    return present


def _modality(text: str) -> str | None:
    """Backward-compatible single-label view; prefers the strictest class."""
    present = _modality_classes(text)
    for name in ("prohibition", "obligation", "permission"):
        if name in present:
            return name
    return None


def _has_negation(text: str) -> bool:
    return bool(_NEGATION_EN.search(text or "") or _NEGATION_ZH.search(text or ""))


def _finding(code: str, message: str, *, evidence: dict | None = None, severity: str = "blocker") -> QaFinding:
    return QaFinding(category="ad", severity=severity, code=code, message=message, evidence=evidence or {})


def _contains(text: str, term: str) -> bool:
    if not term:
        return False
    if any(ord(char) > 127 for char in term):
        return term in text
    # "20 mg" must match "20mg" and vice versa; "flare" must match "flares".
    escaped = re.escape(term).replace(r"\ ", r"\s*")
    escaped = re.sub(r"(?<=\d)(?=[A-Za-zμµ%])", r"\\s*", escaped)
    pattern = r"(?<![A-Za-z0-9])" + escaped + r"(?:s|es)?(?![A-Za-z0-9])"
    return bool(re.search(pattern, text, re.I))


def run_ad_deterministic_qa(context: QaContext) -> list[QaFinding]:
    findings: list[QaFinding] = []
    source = context.source or ""
    target = context.target or ""

    source_numbers, target_numbers = Counter(_numbers(source)), Counter(_numbers(target))
    missing = sorted((source_numbers - target_numbers).elements())
    added = sorted((target_numbers - source_numbers).elements())
    if missing or added:
        findings.append(
            _finding(
                "AD_NUMBER_DRIFT",
                "保护性数字、剂量或统计量在译文中发生变化",
                evidence={"missing_in_target": missing[:20], "unexpected_in_target": added[:20]},
            )
        )

    normalized_source = unicodedata.normalize("NFKC", source)
    normalized_target = unicodedata.normalize("NFKC", target)
    for source_term, target_term in context.terms.items():
        if not source_term or not _contains(normalized_source, source_term):
            continue
        accepted = [target_term, *context.aliases.get(source_term, ())]
        if not any(_contains(normalized_target, item) for item in accepted if item):
            findings.append(
                _finding(
                    "AD_TERM_MISSING",
                    f"批准术语未按策略出现：{source_term} → {target_term}",
                    evidence={"source_term": source_term, "expected_target": target_term, "accepted_aliases": accepted[1:]},
                )
            )

    source_negative = _has_negation(source)
    target_negative = _has_negation(target)
    # Only a dropped negation is flagged at document level; English uses
    # "no/not" far more often than the conservative Chinese marker list.
    if source_negative and not target_negative:
        findings.append(
            _finding(
                "AD_NEGATION_DRIFT",
                "否定语义在译文中发生变化",
                evidence={"source_negative": source_negative, "target_negative": target_negative},
            )
        )

    source_modality, target_modality = _modality_classes(source), _modality_classes(target)
    # Document-level presence is only reliable for strong deontic markers.
    dropped = []
    if "prohibition" in source_modality and "prohibition" not in target_modality:
        dropped.append("prohibition")
    if _STRONG_OBLIGATION.search(source) and "obligation" not in target_modality:
        dropped.append("obligation")
    if dropped:
        findings.append(
            _finding(
                "AD_MODALITY_DRIFT",
                "义务、许可或禁止情态在译文中发生变化",
                evidence={"source_modality": sorted(source_modality), "target_modality": sorted(target_modality), "dropped": dropped},
            )
        )

    return findings

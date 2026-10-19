#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-078b b9：在 AD 语料上回放确定性 QA，度量各规则的命中模式（只读，只输出聚合）。

The corpus' "reference" translations are model drafts, not expert gold, so a hit is either a
rule false positive or a genuine error in the draft. This tool therefore does two things:

* **triage** every missing number / dose / frequency automatically: is the same number present
  next to an equivalent (localised) unit, present with a different unit, present elsewhere, or
  absent altogether? "Equivalent unit present" is strong evidence of a format false positive;
  "absent" is a real-miss candidate. Humans then sample each bucket.
* **controls**: delete one protected value from a draft and check the rule notices (recall).

Only counts, rule codes and number/unit tokens are printed; no prose from the documents.

    python3 scripts/plan078-qa-replay.py --corpus var/plan076-ad-corpus [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# unit (as normalised by the QA rules) -> spellings that mean the same thing in a translation
UNIT_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "mg": ("mg", "毫克"),
    "g": ("g", "克"),
    "kg": ("kg", "千克", "公斤"),
    "ml": ("ml", "毫升"),
    "μg": ("μg", "µg", "mcg", "微克"),
    "µg": ("μg", "µg", "mcg", "微克"),
    "mcg": ("μg", "µg", "mcg", "微克"),
    "iu": ("iu", "IU", "国际单位"),
    "%": ("%", "％", "百分"),
}
FREQ_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "QD": ("QD", "每日一次", "每天一次", "每日1次", "每天1次"),
    "BID": ("BID", "每日两次", "每天两次", "每日2次", "每天2次"),
    "TID": ("TID", "每日三次", "每天三次", "每日3次", "每天3次"),
}


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def _shape(token: str) -> str:
    """Digits -> '#', so tokens can be counted without reproducing document values."""
    return re.sub(r"\d", "#", token)


def classify_number(value: str, translated: str) -> str:
    """Where does the number of a 'missing' value go in the translation?"""
    folded = _fold(translated)
    match = re.match(r"^(?P<num>\d+(?:\.\d+)?)(?P<unit>.*)$", _fold(value))
    if not match:
        return "not_numeric"
    number, unit = match.group("num"), match.group("unit").strip().lower()
    occurrences = [m for m in re.finditer(rf"(?<![\d.]){re.escape(number)}(?![\d]|\.\d)", folded)]
    if not occurrences:
        return "absent"
    equivalents = UNIT_EQUIVALENTS.get(unit, (unit,) if unit else ())
    for m in occurrences:
        window = folded[m.end(): m.end() + 6].lstrip()
        if any(window.lower().startswith(e.lower()) for e in equivalents if e):
            return "equivalent_unit_present"
    for m in occurrences:
        window = folded[m.end(): m.end() + 4].lstrip()
        if window and not window[0].isspace() and not re.match(r"[\d.,，。；;:：)）]", window):
            return "present_with_other_unit"
    return "present_elsewhere"


def classify_frequency(value: str, translated: str) -> str:
    folded = _fold(translated)
    if value.upper() in folded.upper():
        return "present"  # the check compared compact text; spacing difference
    q = re.fullmatch(r"Q(\d+)W", value.upper())
    if q:
        n = q.group(1)
        zh_numbers = {"1": "一", "2": "两二", "3": "三", "4": "四", "6": "六", "8": "八"}.get(n, "")
        pattern = rf"每\s*(?:{n}|[{zh_numbers}])\s*周" if zh_numbers else rf"每\s*{n}\s*周"
        return "localised_equivalent_present" if re.search(pattern, folded) else "absent"
    for variant in FREQ_EQUIVALENTS.get(value.upper(), ()):
        if variant in folded:
            return "localised_equivalent_present"
    return "absent"


def load_cases(corpus: Path) -> list[dict[str, Any]]:
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    cases = []
    for case in manifest.get("cases") or []:
        source = corpus / case["source_ref"]
        reference = corpus / case["reference_ref"]
        if source.is_file() and reference.is_file():
            cases.append(
                {
                    "id": case["case_id"],
                    "direction": case["direction"],
                    "source": source.read_text(encoding="utf-8"),
                    "target": reference.read_text(encoding="utf-8"),
                }
            )
    return cases


def run_rules(source: str, target: str, direction: str) -> list[Any]:
    """Every deterministic text rule the pipeline applies to a (source, translation) pair."""
    from qyunslation.pipeline.ad_qa import QaContext, run_ad_deterministic_qa
    from qyunslation.pipeline.ad_termbase import build_ad_term_policy
    from qyunslation.pipeline.qa.pdf_inspect import check_translation_text

    findings = list(
        check_translation_text(
            source_text=source,
            translated_text=target,
            target_is_chinese=direction == "en-zh",
        )
    )
    policy = build_ad_term_policy(source, direction)
    findings.extend(
        run_ad_deterministic_qa(
            QaContext(
                source=source,
                target=target,
                direction=direction,
                terms=policy.get("terms") or {},
                aliases=policy.get("aliases") or {},
            )
        )
    )
    return findings


def replay(cases: list[dict[str, Any]]) -> dict[str, Any]:
    from qyunslation.pipeline.qa import registry

    by_code: dict[str, dict[str, Any]] = {}
    triage: dict[str, Counter] = defaultdict(Counter)
    shapes: dict[str, Counter] = defaultdict(Counter)
    per_direction = Counter(case["direction"] for case in cases)
    for case in cases:
        for finding in run_rules(case["source"], case["target"], case["direction"]):
            entry = by_code.setdefault(
                finding.code,
                {"severity": finding.severity, "cases": set(), "items": 0, "by_direction": Counter()},
            )
            entry["cases"].add(case["id"])
            entry["items"] += 1
            entry["by_direction"][case["direction"]] += 1
            evidence = finding.evidence or {}
            if finding.code == "AD_NUMBER_DRIFT":
                for value in evidence.get("missing_in_target") or []:
                    triage["AD_NUMBER_DRIFT/missing"][classify_number(str(value), case["target"])] += 1
                    shapes["AD_NUMBER_DRIFT/missing"][_shape(str(value))] += 1
                for value in evidence.get("unexpected_in_target") or []:
                    triage["AD_NUMBER_DRIFT/unexpected"][classify_number(str(value), case["source"])] += 1
                    shapes["AD_NUMBER_DRIFT/unexpected"][_shape(str(value))] += 1
            elif finding.code == "LITERAL_MISSING_DOSE":
                for value in evidence.get("missing") or []:
                    triage["LITERAL_MISSING_DOSE"][classify_number(str(value), case["target"])] += 1
                    shapes["LITERAL_MISSING_DOSE"][_shape(str(value))] += 1
            elif finding.code == "LITERAL_MISSING_FREQ":
                for value in evidence.get("missing") or []:
                    triage["LITERAL_MISSING_FREQ"][classify_frequency(str(value), case["target"])] += 1
    rows = []
    for code, entry in sorted(by_code.items(), key=lambda kv: (-len(kv[1]["cases"]), kv[0])):
        rows.append(
            {
                "code": code,
                "class": registry.rule_for(code).rule_class,
                "severity": entry["severity"],
                "cases_hit": len(entry["cases"]),
                "case_share": round(len(entry["cases"]) / max(1, len(cases)), 3),
                "items": entry["items"],
                "by_direction": dict(entry["by_direction"]),
            }
        )
    return {
        "cases": len(cases),
        "per_direction": dict(per_direction),
        "rules": rows,
        "triage": {key: dict(counter.most_common()) for key, counter in triage.items()},
        "token_shapes": {key: dict(counter.most_common(12)) for key, counter in shapes.items()},
    }


# ---- controls: damage one *protected* value and see whether the rule notices -----------------------


def _protected_lines(text: str) -> list[int]:
    from qyunslation.pipeline.ad_qa import _numbers

    return [i for i, line in enumerate(text.splitlines()) if line.strip() and _numbers(line)]


def _alter_a_protected_number(text: str) -> str | None:
    """Change one digit of a number the rule protects, so a wrong value replaces the right one.

    A candidate only counts when the rule itself sees the line's protected values change
    (years, citation markers and the like are deliberately not protected, so altering them
    would test nothing).
    """
    from collections import Counter as _Counter

    from qyunslation.pipeline.ad_qa import _NUMBER_RE, _normalize_numeric_text, _numbers

    lines = text.splitlines()
    for index in _protected_lines(text):
        normalised = _normalize_numeric_text(lines[index])
        before = _Counter(_numbers(lines[index]))
        for match in _NUMBER_RE.finditer(normalised):
            value = match.group("a")
            start, end = match.span("a")
            changed = value[:-1] + str((int(value[-1]) + 1) % 10)
            candidate = normalised[:start] + changed + normalised[end:]
            if _Counter(_numbers(candidate)) != before:
                lines[index] = candidate
                return "\n".join(lines)
    return None


def _omit_a_line_with_numbers(source: str, target: str) -> str | None:
    """Drop the first translated line that carries protected numbers present in the source."""
    from qyunslation.pipeline.ad_qa import _numbers

    shared = set(_numbers(source))
    lines = target.splitlines()
    for index in _protected_lines(target):
        if set(_numbers(lines[index])) & shared:
            return "\n".join(lines[:index] + lines[index + 1:])
    return None


def controls(cases: list[dict[str, Any]]) -> dict[str, Any]:
    from qyunslation.pipeline.qa import registry

    def keys(source: str, target: str, direction: str) -> set[tuple[str, str]]:
        return {
            (f.code, registry.fingerprint(f.code, f.object_id, f.evidence, f.location))
            for f in run_rules(source, target, direction)
        }

    results: dict[str, Counter] = {"omitted_line": Counter(), "altered_number": Counter()}
    for case in cases:
        baseline = keys(case["source"], case["target"], case["direction"])
        for name, mutant in (
            ("omitted_line", _omit_a_line_with_numbers(case["source"], case["target"])),
            ("altered_number", _alter_a_protected_number(case["target"])),
        ):
            if mutant is None:
                results[name]["no_candidate"] += 1
                continue
            new = keys(case["source"], mutant, case["direction"]) - baseline
            results[name]["detected" if any(code == "AD_NUMBER_DRIFT" for code, _ in new) else "missed"] += 1
    out = {}
    for name, counter in results.items():
        tested = counter["detected"] + counter["missed"]
        out[f"AD_NUMBER_DRIFT/{name}"] = {**counter, "recall": round(counter["detected"] / tested, 3) if tested else None}
    return out


def coverage(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """How much of each rule's territory the corpus actually contains (a rule with no material is untested)."""
    from qyunslation.pipeline.ad_qa import _has_negation, _numbers
    from qyunslation.pipeline.qa.pdf_inspect import extract_protected_literals

    totals: Counter = Counter()
    for case in cases:
        literals = extract_protected_literals(case["source"])
        totals["documents"] += 1
        totals["with_protected_numbers"] += bool(_numbers(case["source"]))
        for kind in ("dose", "freq", "email", "url", "ind"):
            totals[f"with_{kind}_literals"] += bool(literals[kind])
            totals[f"{kind}_literals_total"] += len(literals[kind])
        totals["with_negation"] += _has_negation(case["source"])
    return dict(totals)


def render(report: dict[str, Any]) -> str:
    lines = [f"QA 回放：{report['cases']} 组 {report['per_direction']}（参考译文是模型草稿，命中≠一定是误报）", ""]
    lines.append("规则命中（按命中的文档数）：")
    for row in report["rules"]:
        lines.append(
            f"  {row['code']:<28} [{row['class']}/{row['severity']}] 文档 {row['cases_hit']}/{report['cases']}"
            f"（{row['case_share']:.0%}） 条目 {row['items']} {row['by_direction']}"
        )
    lines += ["", "命中分诊（同一数字/频次在译文里的去向）："]
    for key, counts in report["triage"].items():
        lines.append(f"  {key}: {counts}")
    lines += ["", "数值形态（数字替换为 #）："]
    for key, counts in report["token_shapes"].items():
        lines.append(f"  {key}: {counts}")
    lines += ["", "语料覆盖（原文里各规则管辖的材料有多少）：", f"  {report['coverage']}"]
    if "controls" in report:
        lines += ["", "对照实验（破坏译文中一个受保护的数字，数字规则能否发现）："]
        for code, result in report["controls"].items():
            lines.append(f"  {code}: {result}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", default=str(ROOT / "var" / "plan076-ad-corpus"))
    parser.add_argument("--no-controls", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    corpus = Path(args.corpus)
    if not (corpus / "manifest.json").is_file():
        print(f"BLOCKED: no manifest.json under {corpus}", file=sys.stderr)
        return 2
    cases = load_cases(corpus)
    if not cases:
        print("BLOCKED: the manifest lists no readable cases", file=sys.stderr)
        return 2
    report = replay(cases)
    report["coverage"] = coverage(cases)
    if not args.no_controls:
        report["controls"] = controls(cases)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

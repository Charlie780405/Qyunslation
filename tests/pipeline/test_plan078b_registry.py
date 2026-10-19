"""PLAN-078b: every QA code the pipeline can emit is declared once, with plain-Chinese guidance."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from qyunslation.pipeline.qa import registry

PACKAGE = Path(registry.__file__).resolve().parents[2]
CJK = re.compile(r"[一-鿿]")


def _emitted_codes() -> tuple[set[str], set[str]]:
    """(literal codes, f-string prefixes) passed to QaFinding(...) / _finding(...) / detectors."""
    literals: set[str] = set()
    prefixes: set[str] = set()

    def harvest(node: ast.AST) -> None:
        inside_fstring = {
            id(part) for sub in ast.walk(node) if isinstance(sub, ast.JoinedStr) for part in sub.values
        }
        for sub in ast.walk(node):
            if id(sub) in inside_fstring:
                continue
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", sub.value):
                literals.add(sub.value)
            elif isinstance(sub, ast.JoinedStr) and sub.values and isinstance(sub.values[0], ast.Constant):
                prefixes.add(str(sub.values[0].value))

    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "QaFinding":
                for kw in node.keywords:
                    if kw.arg == "code":
                        harvest(kw.value)
            elif name == "_finding" and node.args:
                harvest(node.args[0])
    # codes produced by helper detectors and constants rather than direct QaFinding calls
    literals |= {"IL_MARKUP_LEAK", "TEXT_ENCODING_ARTIFACT", "TEXT_ENCODING_INHERITED"}
    return literals, prefixes


def test_every_emitted_qa_code_is_registered():
    literals, prefixes = _emitted_codes()
    missing = sorted(code for code in literals if not registry.is_registered(code))
    assert not missing, f"QA codes without a registry entry: {missing}"
    for prefix in prefixes:
        assert any(rule.code.startswith(prefix) for rule in registry.all_rules()), prefix


def test_scan_actually_finds_codes():
    literals, _ = _emitted_codes()
    # Guards against the scan silently matching nothing.
    assert {"AD_NUMBER_DRIFT", "LOGO_MISSING", "TERM_EXTRACTION_DEGRADED", "UNTRANSLATED_BODY"} <= literals


@pytest.mark.parametrize("rule", registry.all_rules(), ids=lambda r: r.code)
def test_every_rule_explains_itself_in_chinese(rule):
    assert rule.rule_class in {registry.C1, registry.C2, registry.C3, registry.C4, registry.WARN, registry.INFO}
    for field in (rule.title, rule.why, rule.how):
        assert field.strip() and CJK.search(field), (rule.code, field)


def test_critical_and_dose_rules_are_never_batchable():
    for rule in registry.all_rules():
        if rule.rule_class in {registry.C1, registry.C2, registry.C3}:
            assert not rule.batchable, rule.code
    # D2: dose/frequency stay one-by-one until their false-positive rate is known.
    assert not registry.rule_for("LITERAL_MISSING_DOSE").batchable
    assert not registry.rule_for("LITERAL_MISSING_FREQ").batchable


def test_unknown_code_is_treated_as_critical_and_not_waivable():
    rule = registry.rule_for("SOMETHING_NEW")
    assert rule.rule_class == registry.C1
    assert "SOMETHING_NEW" in rule.title
    assert registry.allowed_actions(rule.rule_class, "admin", is_writer=True) == [
        "report_false_positive",
        "confirm_false_positive",
        "reject_false_positive",
    ]


def test_fingerprint_is_stable_and_distinguishes_problems():
    a = registry.fingerprint("AD_NUMBER_DRIFT", None, {"missing_in_target": ["5", "3"], "unexpected_in_target": []})
    same = registry.fingerprint("AD_NUMBER_DRIFT", None, {"missing_in_target": ["3", "5"], "unexpected_in_target": [], "direction": "x"})
    other = registry.fingerprint("AD_NUMBER_DRIFT", None, {"missing_in_target": ["3"], "unexpected_in_target": []})
    assert a == same  # order and unrelated evidence do not matter
    assert a != other  # a different set of drifting numbers is a different problem
    assert registry.fingerprint("LOGO_MISSING", None, {"output_kind": "mono"}) != registry.fingerprint(
        "LOGO_MISSING", None, {"output_kind": "dual"}
    )


@pytest.mark.parametrize(
    "rule_class,role,writer,expected",
    [
        (registry.C1, "member", True, ["report_false_positive"]),
        (registry.C1, "reviewer", False, ["report_false_positive"]),  # reviewers may report, not confirm
        (registry.C1, "term_admin", False, ["report_false_positive", "confirm_false_positive", "reject_false_positive"]),
        (registry.C2, "reviewer", False, ["report_false_positive", "grant_waiver", "revoke_waiver"]),
        (registry.C2, "member", True, ["report_false_positive"]),  # a submitter alone cannot waive
        (registry.C3, "admin", True, []),  # nothing to dispose of: re-run the check
        (registry.WARN, "member", True, ["acknowledge", "report_false_positive"]),
    ],
)
def test_who_may_do_what(rule_class, role, writer, expected):
    assert registry.allowed_actions(rule_class, role, is_writer=writer) == expected


def test_rule_set_version_tracks_rule_files():
    version = registry.rule_set_version()
    assert re.fullmatch(r"qa-[0-9a-f]{12}", version)
    assert registry.rule_set_version() == version  # cached and stable within a process

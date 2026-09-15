#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-063：规则进化与质量台账三态门禁。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

if [[ ! -x "$PY" ]]; then
  fail "Python interpreter unavailable; set QYUNSLATION_VERIFY_PY"
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-063-translation-quality-evolution"
for required in \
  "$PLAN_DIR/README.md" \
  "$PLAN_DIR/PLAN-063a-decision-feedback-rules.md" \
  "$PLAN_DIR/PLAN-063b-domain-accuracy-ledger.md" \
  "$PLAN_DIR/PLAN-063c-quality-evolution-skill.md" \
  "$PLAN_DIR/PLAN-063d-verification-delivery.md" \
  "$PLAN_DIR/PLAN-063e-062-closeout.md" \
  "$ROOT/docs/walkthroughs/WT-063-translation-quality-evolution.md" \
  "$ROOT/glossaries/term-exclusions.csv" \
  "$ROOT/qyunslation/quality/ledger.py" \
  "$ROOT/scripts/plan063-evolve-term-rules.py" \
  "$ROOT/scripts/plan063-quality-report.py" \
  "$ROOT/scripts/plan063e-backfill-machine-decisions.py" \
  "$ROOT/.cursor/skills/translation-quality-evolution/SKILL.md" \
  "$ROOT/docs/decisions/ADR-032-term-rule-evolution-human-promote.md"; do
  [[ -f "$required" ]] && pass "static $(basename "$required")" || fail "missing $required"
done

head -n 1 "$ROOT/glossaries/term-exclusions.csv" | grep -q 'source,reason,scope' \
  && pass "exclusions schema" || fail "exclusions schema"

grep -q 'PLAN-063-translation-quality-evolution' "$ROOT/docs/plans/README.md" \
  && pass "plans index PLAN-063" || fail "plans index missing PLAN-063"
grep -q 'version = "063-v1"' "$ROOT/glossaries/term-candidate-rules.toml" \
  && pass "rules version 063-v1" || fail "rules version is not 063-v1"

SIG="$ROOT/.cursor/skills/skill-registry/error-signatures.toml"
for id in SIG-TERM-SAVE-SWALLOWED SIG-TERM-COLUMNS-EMPTY SIG-TERM-CANDIDATE-NOISE \
  SIG-TERM-SCREEN-BLIND SIG-GUI-PATCH-STALE SIG-RULES-VERSION-DRIFT; do
  grep -q "$id" "$SIG" && pass "signature $id" || fail "missing $id"
done
grep -q 'SK-Q011' "$ROOT/.cursor/skills/skill-registry/registry.md" \
  && pass "registry SK-Q011" || fail "registry missing SK-Q011"

if "$PY" -m compileall -q \
  qyunslation/quality \
  scripts/plan063-evolve-term-rules.py \
  scripts/plan063-quality-report.py \
  scripts/plan063e-backfill-machine-decisions.py; then
  pass "PLAN-063 modules compile"
else
  fail "PLAN-063 modules compile"
fi

if "$PY" -m pytest -q --no-cov \
  tests/quality/test_plan063_ledger.py \
  tests/scripts/test_plan063_evolve_rules.py \
  tests/persist/test_plan063_migration.py \
  tests/workbench/test_plan063e_machine_decision.py \
  tests/workbench/test_plan063_batch_guard.py \
  tests/workbench/test_plan062_purge.py \
  tests/workbench/test_plan061_candidate_rules.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "PLAN-063 focused pytest"
else
  fail "PLAN-063 focused pytest"
  tail -n 80 "$STAGE_DIR/pytest.log" || true
fi

if "$PY" scripts/plan063-evolve-term-rules.py --report --dry-run >"$STAGE_DIR/report.log" 2>&1; then
  pass "evolve --report --dry-run"
else
  fail "evolve --report --dry-run"
  tail -n 40 "$STAGE_DIR/report.log" || true
fi

"$PY" - <<'PY' && pass "rules fingerprint registered" || fail "rules fingerprint not registered"
from pathlib import Path
from qyunslation.glossary.candidate_rules import load_rules, rules_fingerprint, rules_version
load_rules.cache_clear()
fp = rules_fingerprint()
ver = rules_version()
text = Path(".cursor/skills/skill-registry/term-rules-versions.md").read_text(encoding="utf-8")
assert ver in text and fp in text, (ver, fp)
PY

GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
if [[ -f "$GUI" ]]; then
  missing=0
  for mark in _qy_tbl_progress "0.96 + 0.03" 需人工填写 术语未遵循 keep_selection; do
    grep -q "$mark" "$GUI" || missing=1
  done
  [[ "$missing" == "0" ]] && pass "gui patch marker parity" || fail "gui patch marker parity"
else
  blocked "installed gui.py missing"
fi

WT062="$ROOT/docs/walkthroughs/WT-062-termbase-evolution.md"
if grep -q '进度条' "$WT062" && grep -qE '保存后自动进入下一条|保存下一条' "$WT062" && grep -q '关联已有词条' "$WT062"; then
  if grep -Eq '须再译一篇|待真实文档补证|待补 LIVE' "$WT062"; then
    blocked "PLAN-062 LIVE three items still need a real document"
  else
    pass "PLAN-062 LIVE documented"
  fi
else
  fail "WT-062 missing LIVE checklist"
fi

if [[ "${QYUNSLATION_PLAN063_FULL:-0}" == "1" ]]; then
  if bash "$ROOT/scripts/verify-plan-062.sh" >"$STAGE_DIR/v062.log" 2>&1; then
    pass "verify-plan-062 dependency"
  else
    blocked "verify-plan-062 did not pass"
    tail -n 20 "$STAGE_DIR/v062.log" || true
  fi
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%s fail=0\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0\n'
exit 0

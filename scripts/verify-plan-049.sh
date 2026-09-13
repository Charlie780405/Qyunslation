#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-049 literature table leave BabelDOC.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  PY="$ROOT/.venv/bin/python"
fi
STAGE_DIR="$(mktemp -d)"
FAILURES=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL fail=1\n'
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-049-literature-table-leave-babeldoc"
[[ -f "$PLAN_DIR/PLAN-049-literature-table-leave-babeldoc.md" ]] \
  && pass "PLAN-049 charter" || fail "missing PLAN-049 charter"
for f in PLAN-049a-skip-literature-paint.md PLAN-049b-047d-numeric-guard.md \
  PLAN-049c-table2-font-only.md PLAN-049d-verify-docs.md PLAN-049e-column-center.md \
  PLAN-049f-latin-ascii-origin-rows.md PLAN-049g-hpd-font-rules.md \
  PLAN-049h-hpd-cell-write.md PLAN-049i-n-eq-overlap-easi.md \
  PLAN-049j-table3-token-unglue.md; do
  [[ -f "$PLAN_DIR/$f" ]] && pass "$f" || fail "missing $f"
done

grep -q 'literature_leave_babeldoc' "$ROOT/scripts/pdf_table_translate.py" \
  && pass "049a skip paint" || fail "049a missing literature_leave_babeldoc"
if grep -q 'if literature:' "$ROOT/scripts/pdf_table_translate.py" \
  && grep -q 'return src_path' "$ROOT/scripts/pdf_table_translate.py"; then
  pass "049a no tblnorm fallback for literature"
else
  fail "049a literature still hits tblnorm"
fi

grep -q '_numeric_cell' "$ROOT/scripts/apply-pdf2zh-047d-para-layout.py" \
  && pass "049b numeric guard" || fail "049b missing _numeric_cell"

grep -q 'allow_translate' "$ROOT/scripts/pdf_table_normalize.py" \
  && pass "049c allow_translate" || fail "049c missing allow_translate"
grep -q 'allow_translate=not literature' "$ROOT/scripts/pdf_table_translate.py" \
  && pass "049c font-only narrow tables" || fail "049c missing font-only call"

grep -q 'center_table_region' "$ROOT/scripts/pdf_table_translate.py" \
  && grep -q 'PLAN-049e' "$ROOT/scripts/pdf_table_column_center.py" \
  && ! grep -q 'redact_table_region' "$ROOT/scripts/pdf_table_column_center.py" \
  && pass "049e column center" || fail "049e missing center_table_region"

if grep -q 'normalize_ascii' "$ROOT/scripts/pdf_table_column_center.py" \
  && grep -q 'prefer_origin_abbrev\|_origin_y1\|PLAN-049' "$ROOT/scripts/pdf_table_column_center.py"; then
  pass "049f latin ascii + origin rows"
else
  fail "049f missing normalize_ascii/origin rows"
fi

if grep -q 'hpd_column_ranges' "$ROOT/scripts/pdf_table_column_center.py" \
  && grep -q 'restore_rule_lines' "$ROOT/scripts/pdf_table_column_center.py" \
  && grep -q 'qy-tbl' "$ROOT/scripts/pdf_table_column_center.py"; then
  pass "049g hpd columns + rules + noto"
else
  fail "049g missing hpd/rules/qy-tbl"
fi

if grep -q 'header_slots_from_blob' "$ROOT/scripts/pdf_table_column_center.py" \
  && grep -q 'lock_visit_column' "$ROOT/scripts/pdf_table_column_center.py" \
  && grep -q '_fit_cell_lines' "$ROOT/scripts/pdf_table_column_center.py"; then
  pass "049h hpd cell write"
else
  fail "049h missing header/visit/fit"
fi

if grep -q 'header_n_eq_texts' "$ROOT/scripts/pdf_table_column_center.py" \
  && grep -q '_safe_bands' "$ROOT/scripts/pdf_table_column_center.py" \
  && grep -q 'should_center_literature_table' "$ROOT/scripts/pdf_table_translate.py"; then
  pass "049i n-eq / bands / table2"
else
  fail "049i missing n-eq/bands/table2"
fi

if grep -q 'assign_by_origin_shapes' "$ROOT/scripts/pdf_table_column_center.py" \
  && grep -q 'origin_cell_shape' "$ROOT/scripts/pdf_table_column_center.py" \
  && grep -qE '90\.0111\.2|Q\[24\]W\)\(' "$ROOT/scripts/pdf_table_column_center.py"; then
  pass "049j token unglue"
else
  fail "049j missing origin-shape peel"
fi

SKILL="$ROOT/.cursor/skills/table-translation-fidelity/SKILL.md"
grep -q 'LITERATURE_LEAVE_BABELDOC\|文献默认不落笔\|交还 BabelDOC' "$SKILL" \
  && pass "SK-Q009 updated" || fail "SK-Q009 missing 049 rule"
grep -q '表内西文半角\|normalize_ascii\|049f' "$SKILL" \
  && pass "SK-Q009 049f" || fail "SK-Q009 missing 049f rule"
grep -q '三线从原文补\|restore_rule_lines\|049g' "$SKILL" \
  && pass "SK-Q009 049g" || fail "SK-Q009 missing 049g rule"
grep -q '表头按格写\|_fit_cell_lines\|049h\|HPD \*\*格\*\*' "$SKILL" \
  && pass "SK-Q009 049h" || fail "SK-Q009 missing 049h rule"
grep -q '049i\|表头 N=\|矮窄' "$SKILL" \
  && pass "SK-Q009 049i" || fail "SK-Q009 missing 049i rule"
grep -q '049j\|粘连切分\|origin.*形态\|90\.0111' "$SKILL" \
  && pass "SK-Q009 049j" || fail "SK-Q009 missing 049j rule"

if "$PY" -m pytest -q --no-cov tests/structure/test_plan049_literature_leave.py \
  tests/structure/test_plan041_quality_gates.py \
  -k 'not plan041_real_sample' >"$STAGE_DIR/py.log" 2>&1; then
  pass "pytest 049/041"
else
  fail "pytest"
  tail -n 40 "$STAGE_DIR/py.log"
fi

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%s\n' "$FAILURES"
exit 1

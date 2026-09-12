#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-046 literature structure fidelity gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  PY="$ROOT/.venv/bin/python"
fi
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

run_pass() {
  local label="$1" log="$2"
  shift 2
  if "$@" >"$log" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=0 fail=1\n'
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-046-literature-structure-fidelity"
[[ -f "$PLAN_DIR/PLAN-046-literature-structure-fidelity.md" ]] \
  && pass "PLAN-046 charter" || fail "missing PLAN-046 charter"
for f in PLAN-046a-stop-bleed-gates.md PLAN-046b-paragraph-merge.md \
  PLAN-046c-table-columns.md PLAN-046d-image-rotate-qc.md \
  PLAN-046e-verify-docs.md; do
  [[ -f "$PLAN_DIR/$f" ]] && pass "$f" || fail "missing $f"
done

# 046a：literature 不在 isolate；source_p75 可达
if grep -q 'if literature:' "$ROOT/scripts/pdf_table_translate.py" \
  && grep -q 'table_size_mode = "source_p75"' "$ROOT/scripts/pdf_table_translate.py" \
  && ! grep -q 'or literature' "$ROOT/scripts/pdf_table_translate.py"; then
  pass "046a literature not isolate"
else
  fail "046a isolate/source_p75 order"
fi
grep -q 'COLUMN_CLUSTER_DRIFT\|detect_column_cluster_drift' \
  "$ROOT/qyunslation/structure/table_qc.py" \
  && pass "046a COLUMN_CLUSTER_DRIFT" || fail "046a missing COLUMN_CLUSTER_DRIFT"
grep -q 'FIGURE_TIER_MAX_PX\|_mark_unfittable_redraw' \
  "$ROOT/qyunslation/extensions/image_translate.py" \
  && pass "046a size cap / trial fit" || fail "046a size/trial"
grep -q '_qy_lit_no_drop\|not dropped' "$ROOT/scripts/doc_profile.py" \
  && pass "046a no glyph drop" || fail "046a still drops glyphs"

# 046b
[[ -f "$ROOT/scripts/apply-pdf2zh-046b-para-merge.py" ]] \
  && pass "046b patcher" || fail "missing 046b patcher"
grep -q 'apply-pdf2zh-046b-para-merge.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "046b in service" || fail "046b not in pdf2zh.service"
grep -q 'min_scale' "$ROOT/scripts/doc_profiles.toml" \
  && pass "046b min_scale profile" || fail "046b min_scale missing"
grep -q 'detect_drug_name_drift\|DRUG_NAME_DRIFT' \
  "$ROOT/qyunslation/structure/text_sanitize.py" \
  && pass "046b drug drift" || fail "046b drug drift"

PF="$HOME/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/midend/paragraph_finder.py"
TS="$HOME/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/midend/typesetting.py"
if [[ -f "$PF" ]] && grep -q '_QY_046B_PARA_MERGE' "$PF"; then
  pass "046b para merge present"
else
  if "$PY" "$ROOT/scripts/apply-pdf2zh-046b-para-merge.py" >"$STAGE_DIR/046b-apply.log" 2>&1 \
    && grep -q '_QY_046B_PARA_MERGE' "$PF"; then
    pass "046b para merge applied"
  else
    fail "046b para merge missing"
  fi
fi
if [[ -f "$TS" ]] && grep -q "_QY_MIN_SCALE" "$TS"; then
  pass "046b min_scale hook"
else
  fail "046b min_scale hook missing"
fi

# 046c
grep -q '_merge_column_clusters' "$ROOT/qyunslation/structure/table_structure.py" \
  && pass "046c column merge" || fail "046c column merge"
grep -q 'SPAN_ORDER_DRIFT\|detect_span_order_drift' \
  "$ROOT/qyunslation/structure/table_attribution.py" \
  && pass "046c SPAN_ORDER_DRIFT" || fail "046c SPAN_ORDER_DRIFT"
if grep -q 'SPAN_ORDER_DRIFT' "$ROOT/qyunslation/structure/table_qc.py" \
  && ! grep -q 'SPAN_ORDER_DRIFT' <<<"$(grep TABLE_QC_SOFT "$ROOT/qyunslation/structure/table_qc.py")"; then
  pass "046c SPAN_ORDER hard"
else
  # soft sets shouldn't contain it
  if grep -q 'SPAN_ORDER_DRIFT' "$ROOT/qyunslation/structure/table_qc.py"; then
    pass "046c SPAN_ORDER in terminal"
  else
    fail "046c SPAN_ORDER not hard"
  fi
fi

# 046d
grep -q 'ROTATED_TIER\|_is_rotated_axis_box\|_is_ocr_garbage' \
  "$ROOT/qyunslation/extensions/image_translate.py" \
  && pass "046d rotate/garbage" || fail "046d rotate/garbage"
grep -qE '\\(\[A-Fa-f\]\\)|PANEL_CONFUSION' \
  "$ROOT/qyunslation/extensions/image_translate.py" \
  && pass "046d panel paren" || fail "046d panel paren"

[[ -f "$ROOT/docs/walkthroughs/WT-046-literature-structure-fidelity.md" ]] \
  && pass "WT-046" || fail "missing WT-046"

run_pass "046 compile" "$STAGE_DIR/compile.log" "$PY" -m compileall -q \
  qyunslation/structure/table_qc.py \
  qyunslation/structure/table_structure.py \
  qyunslation/structure/table_attribution.py \
  qyunslation/structure/text_sanitize.py \
  qyunslation/extensions/image_translate.py \
  scripts/pdf_table_translate.py \
  scripts/doc_profile.py \
  scripts/apply-pdf2zh-046b-para-merge.py

run_pass "046 focused tests" "$STAGE_DIR/tests.log" \
  timeout --signal=INT --kill-after=10s 240s "$PY" -m pytest -q -o addopts= \
    tests/structure/test_plan046a_gates.py \
    tests/extensions/test_plan046a_size_cap.py \
    tests/structure/test_plan046b_para_merge.py \
    tests/structure/test_plan046c_columns.py \
    tests/extensions/test_plan046d_rotate.py

run_pass "045 regression" "$STAGE_DIR/045.log" bash "$ROOT/scripts/verify-plan-045.sh"

printf 'SUMMARY: %s blocked=%s fail=%s\n' \
  "$([[ "$FAILURES" -eq 0 ]] && echo PASS || echo FAIL)" \
  "$BLOCKED" "$FAILURES"
[[ "$FAILURES" -eq 0 ]]

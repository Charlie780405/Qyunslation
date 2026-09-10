#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-037 P1-A/P1-B：表格执行可观测 + PPT policy 执行门。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then pass "$label"
  else fail "$label"; tail -n 30 "$log_path"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1\n'
  exit 1
fi

run_pass "037 compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure/table_execution_observability.py \
    qyunslation/structure/pptx_table_exec.py \
    qyunslation/custom_api.py \
    qyunslation/translator/ai_translator/pptx_translator.py \
    scripts/doc_image_prescan.py \
    scripts/pdf_table_translate.py

run_pass "037 observability tests" "$STAGE_DIR/tests.log" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_table_execution_observability.py \
    tests/structure/test_plan037_pptx_table_exec.py \
    tests/structure/test_plan030ib_manifest_download.py

grep -q "execution_table_fidelity_hint" "$ROOT/scripts/apply-pdf2zh-docimg.py" \
  && pass "docimg execution fidelity hook" \
  || fail "docimg execution fidelity hook"

grep -q "table_fidelity_hint" "$ROOT/scripts/apply-pdf2zh-prescan.py" \
  && pass "prescan table fidelity hook" \
  || fail "prescan table fidelity hook"

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1

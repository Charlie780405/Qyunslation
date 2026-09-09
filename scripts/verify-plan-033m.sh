#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-033m honest gate + wiring. Do not nest 028-030h.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
GUI="${QYUNSLATION_PDF2ZH_GUI:-/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-180}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
show_failure_log() { [[ -f "$1" ]] && tail -n 40 "$1"; }

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then pass "$label"
  else fail "$label"; show_failure_log "$log_path"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

run_pass "033m modules compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure/plan033_final.py \
    qyunslation/structure/scan_pdf.py \
    qyunslation/structure/models.py \
    scripts/apply-pdf2zh-docimg.py \
    scripts/pdf_table_translate.py \
    scripts/pdf_image_translate.py

run_pass "033m unit tests" "$STAGE_DIR/unit.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_plan033m_honest_gate.py \
    tests/structure/test_plan033l_inspect.py \
    tests/test_plan033c_imgtr_post.py

if [[ -f "$GUI" ]]; then
  run_pass "apply docimg harden" "$STAGE_DIR/patch.log" "$PY" scripts/apply-pdf2zh-docimg.py
  if grep -q '表格写出跳过' "$GUI"; then
    fail "installed GUI still soft-swallows tbltr"
  else
    pass "installed GUI hard-fails tbltr"
  fi
  if grep -q 'bind_task_model_trace' "$GUI"; then
    pass "installed GUI binds model_trace"
  else
    fail "installed GUI missing model_trace bind"
  fi
fi

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1

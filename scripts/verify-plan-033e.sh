#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-033e preview DPI + semantic progress gate. Do not nest 028-030h.
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

run_pass "PLAN-033e modules compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    scripts/pdf_preview_pages.py \
    scripts/apply-pdf2zh-preview-dpi.py \
    qyunslation/structure/progress.py

run_pass "PLAN-033e unit tests" "$STAGE_DIR/unit.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/test_plan033e_preview.py

if [[ -f "$GUI" ]]; then
  run_pass "apply preview-dpi patch" "$STAGE_DIR/patch.log" \
    "$PY" scripts/apply-pdf2zh-preview-dpi.py
  if grep -q '__qyPreviewHiDpi = 300' "$GUI" && grep -q '_qy_preview_dpi' "$GUI"; then
    pass "installed GUI has 300 DPI current-page hook"
  else
    fail "installed GUI missing 300 DPI hook"
  fi
  if grep -q 'apply-pdf2zh-preview-dpi.py' "$ROOT/scripts/pdf2zh.service"; then
    pass "service wires preview-dpi"
  else
    fail "service missing preview-dpi ExecStartPre"
  fi
else
  printf 'INFO: pdf2zh GUI not installed, skip live patch checks\n'
fi

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1

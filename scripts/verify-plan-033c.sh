#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-033c original-immutable gate. Do not nest 028-030h.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
GUI="${QYUNSLATION_PDF2ZH_GUI:-/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py}"
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

run_pass "PLAN-033c modules compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q scripts/pdf_image_translate.py scripts/apply-pdf2zh-docimg.py

run_pass "PLAN-033c unit tests" "$STAGE_DIR/unit.log" \
  "$PY" -m pytest -q --no-cov tests/test_plan033c_imgtr_post.py

run_pass "PLAN-033a still passes" "$STAGE_DIR/033a.log" \
  bash scripts/verify-plan-033a.sh

if [[ -f "$GUI" ]]; then
  run_pass "apply imgtr post patch" "$STAGE_DIR/patch.log" \
    "$PY" scripts/apply-pdf2zh-docimg.py
  if grep -q 'file_path = _qy_new' "$GUI"; then
    fail "installed GUI still swaps BabelDOC input to imgtr"
  else
    pass "installed GUI no longer swaps BabelDOC input"
  fi
  if grep -q '_qy_imgtr_post' "$GUI" && grep -q 'x_min_frac' "$GUI"; then
    pass "installed GUI has post-translate imgtr"
  else
    fail "installed GUI missing post-translate imgtr"
  fi
  if grep -q '_pre_imgtr_origin_path' "$GUI"; then
    pass "PLAN-027 origin hook still present"
  else
    fail "PLAN-027 origin hook missing"
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

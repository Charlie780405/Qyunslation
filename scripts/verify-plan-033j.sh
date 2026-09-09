#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
STAGE_DIR="$(mktemp -d)"; FAILURES=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
run_pass() { local label="$1" log="$2"; shift 2; if "$@" >"$log" 2>&1; then pass "$label"; else fail "$label"; tail -n 40 "$log"; fi; }
if [[ ! -x "$PY" ]]; then printf 'SUMMARY: FAIL blocked=1 fail=0\n'; exit 1; fi
run_pass "033j compile" "$STAGE_DIR/c.log" "$PY" -m compileall -q \
  qyunslation/structure/table_translate.py \
  qyunslation/structure/protect.py \
  qyunslation/structure/table_writeback.py \
  scripts/pdf_table_translate.py \
  scripts/apply-pdf2zh-docimg.py
run_pass "033j tests" "$STAGE_DIR/t.log" timeout --signal=INT --kill-after=10s 180s "$PY" -m pytest -q --no-cov \
  tests/structure/test_plan033j_table_translate.py \
  tests/structure/test_plan033_table_image_prod.py
if [[ "$FAILURES" -eq 0 ]]; then printf 'SUMMARY: PASS fail=0\n'; exit 0; fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"; exit 1

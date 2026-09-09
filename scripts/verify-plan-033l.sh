#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-033l final PDF gate. Sample missing => BLOCKED, never skip-pass.
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

if [[ -z "${QYUNSLATION_PLAN033_SAMPLE:-}" ]]; then
  for cand in \
    "/home/dev/.hermes/attachments/1-s2.0-S2666636725013958-main.pdf" \
    "/home/dev/pdf2zh/pdf2zh_files/d10bbff3-0701-431b-ad9e-9992f4f7792c/1-s2.0-S2666636725013958-main.pdf"
  do
    if [[ -f "$cand" ]]; then
      export QYUNSLATION_PLAN033_SAMPLE="$cand"
      break
    fi
  done
fi

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log_path"; fi
}

run_pass "033l modules compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q qyunslation/structure/plan033_final.py \
  qyunslation/structure/model_trace.py scripts/check-babeldoc-fidelity-033l.py
run_pass "033l inspect tests" "$STAGE_DIR/inspect.log" \
  timeout --signal=INT --kill-after=10s 60s "$PY" -m pytest -q --no-cov \
  tests/structure/test_plan033l_inspect.py

if ! grep -q 'apply-pdf2zh-fidelity-033h.py' "$ROOT/scripts/pdf2zh.service"; then
  fail "pdf2zh.service missing 033h ExecStartPre"
else
  pass "pdf2zh.service lists 033h patch"
fi
if ! grep -q 'office.env' "$ROOT/scripts/pdf2zh.service"; then
  fail "pdf2zh.service missing office.env"
else
  pass "pdf2zh.service loads office.env"
fi

"$PY" - <<'PY' >"$STAGE_DIR/final.json"
import json
from qyunslation.structure.plan033_final import inspect_final, patch_signature
report = inspect_final()
report["patch_signature"] = patch_signature()
print(json.dumps(report, ensure_ascii=False, indent=2))
PY
status=$?
if [[ $status -ne 0 ]]; then
  fail "inspect_final crashed"
  tail -n 40 "$STAGE_DIR/final.json"
else
  pass "inspect_final ran"
fi

if [[ -f "$STAGE_DIR/final.json" ]]; then
  if grep -q '"SAMPLE_MISSING"' "$STAGE_DIR/final.json"; then
    blocked "QYUNSLATION_PLAN033_SAMPLE missing"
  fi
  if grep -q '"FINAL_PDF_MISSING"' "$STAGE_DIR/final.json"; then
    blocked "final mono/dual PDF missing"
  fi
  if grep -q '"fail": \[' "$STAGE_DIR/final.json"; then
    fail_n=$("$PY" -c "import json; print(len(json.load(open('$STAGE_DIR/final.json'))['fail']))")
    if [[ "$fail_n" != "0" ]]; then
      fail "final PDF assertions fail=$fail_n"
      "$PY" -c "import json; print('\n'.join(json.load(open('$STAGE_DIR/final.json'))['fail']))"
    else
      pass "final PDF assertions"
    fi
  fi
fi

if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%d fail=%d\n' "$BLOCKED" "$FAILURES"
  exit 2
fi
if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1

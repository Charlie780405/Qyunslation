#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-033n：HEAD 绑定产物 + 033l 总门。样本缺失 => BLOCKED。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
STEM="1-s2.0-S2666636725013958-main.no_watermark.zh"

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

HEAD="$(git rev-parse --short HEAD)"
STAGING="/tmp/plan033m-${HEAD}"

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

if [[ -x "$ROOT/scripts/rerun-plan033-head-evidence.sh" ]]; then
  pass "rerun script present"
else
  fail "rerun-plan033-head-evidence.sh missing"
fi

if "$PY" -m compileall -q qyunslation/structure/plan033_final.py >"$STAGE_DIR/compile.log" 2>&1; then
  pass "033n modules compile"
else
  fail "033n modules compile"
fi

if [[ ! -d "$STAGING" ]] || [[ ! -f "$STAGING/${STEM}.mono.imgtr.tbltr.pdf" ]]; then
  blocked "HEAD staging missing: $STAGING (run bash scripts/rerun-plan033-head-evidence.sh)"
else
  pass "HEAD staging present: $STAGING"
  if [[ -f "$STAGING/HEAD" ]] && [[ "$(cat "$STAGING/HEAD")" == "$HEAD" ]]; then
    pass "HEAD marker matches"
  else
    fail "HEAD marker mismatch"
  fi
fi

if [[ "$BLOCKED" -eq 0 ]]; then
  if bash "$ROOT/scripts/verify-plan-033l.sh" >"$STAGE_DIR/033l.log" 2>&1; then
    pass "verify-plan-033l.sh"
  else
    fail "verify-plan-033l.sh"
    tail -n 30 "$STAGE_DIR/033l.log"
  fi
fi

if [[ "$BLOCKED" -eq 0 ]] && [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0 blocked=0\n'
  exit 0
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%d fail=%d\n' "$BLOCKED" "$FAILURES"
  exit 2
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1

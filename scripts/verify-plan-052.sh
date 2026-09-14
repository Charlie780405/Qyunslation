#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-052：金标真件补齐门（默认工程 PASS；REQUIRE_R_REAL=1 才强制 R≥1）。
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

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL fail=1 blocked=0\n'
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-052-gold-real-fill"
WT="$ROOT/docs/walkthroughs/WT-052-gold-real-fill.md"

[[ -f "$PLAN_DIR/PLAN-052-gold-real-fill.md" ]] && pass "PLAN-052 charter" || fail "PLAN-052 charter"
[[ -f "$PLAN_DIR/PLAN-052a-promote-inbox.md" ]] && pass "PLAN-052a" || fail "PLAN-052a"
[[ -f "$PLAN_DIR/PLAN-052b-c-protocol-candidates.md" ]] && pass "PLAN-052b" || fail "PLAN-052b"
[[ -f "$PLAN_DIR/PLAN-052c-verify-gate.md" ]] && pass "PLAN-052c" || fail "PLAN-052c"
[[ -f "$WT" ]] && pass "WT-052" || fail "WT-052"
[[ -f "$ROOT/scripts/plan052-promote-gold.py" ]] && pass "promote script" || fail "promote script"
[[ -f "$ROOT/qyunslation/gold/plan052_promote.py" ]] && pass "promote module" || fail "promote module"
[[ -f "$ROOT/docs/gold/plan034/real-sources.json" ]] && pass "real-sources.json" || fail "real-sources.json"

if "$PY" -m pytest -q --no-cov tests/gold/test_plan052_promote.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "plan052 pytest"
else
  fail "plan052 pytest"
  tail -n 40 "$STAGE_DIR/pytest.log" || true
fi

# 景行例文登记：方案→C protocol；CDP→C cdp；M2.5 综述→R ctd-m2
if "$PY" -c "
from qyunslation.gold.plan052_promote import load_real_sources, assert_kind_allowed
data = load_real_sources()
by = {e['entry_id']: e for e in data['entries']}
assert by['C-06']['class']=='C' and by['C-06']['kind']=='protocol'
assert by['C-07']['class']=='C' and by['C-07']['kind']=='cdp'
assert by['R-01']['class']=='R' and by['R-01']['kind']=='ctd-m2'
assert_kind_allowed('C','protocol'); assert_kind_allowed('C','cdp'); assert_kind_allowed('R','ctd-m2')
print('gs101 map ok')
" >"$STAGE_DIR/map.log" 2>&1; then
  pass "GS101 Protocol/CDP/M2.5 class map"
else
  fail "GS101 Protocol/CDP/M2.5 class map"
  cat "$STAGE_DIR/map.log" || true
fi

COUNTS="$("$PY" -c "
from qyunslation.gold.plan052_promote import real_counts, product_ready
c = real_counts()
print(f\"L={c['L']} C={c['C']} R={c['R']} total={c['total']} product_ready={'yes' if product_ready(c) else 'no'}\")
")"
printf '%s\n' "$COUNTS"
if [[ "$COUNTS" == *'product_ready=yes'* ]]; then
  pass "product_ready=yes"
else
  printf 'product_ready=no (R real still 0 until M2.5 inbox promote)\n'
fi

if [[ "${QYUNSLATION_PLAN052_REQUIRE_R_REAL:-}" == "1" || "${QYUNSLATION_PLAN052_REQUIRE_R_REAL:-}" == "true" ]]; then
  if [[ "$COUNTS" == *'product_ready=yes'* ]]; then
    pass "REQUIRE_R_REAL satisfied"
  else
    blocked "REQUIRE_R_REAL: R has no real gold (drop GS101 M2.5 into inbox/R and promote R-01)"
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

#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034a gold catalog + Pharma-MQM + thresholds. Missing gold → BLOCKED.
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
  if "$@" >"$log" 2>&1; then
    pass "$label"
  else
    fail "$label"
    tail -n 40 "$log"
  fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL fail=1 blocked=0\n'
  exit 1
fi

PLAN_A="$ROOT/docs/plans/PLAN-034-pharma-rd-mvp/PLAN-034a-gold-benchmark.md"
GOLD="$ROOT/docs/gold/plan034"
[[ -f "$PLAN_A" ]] && pass "PLAN-034a doc" || fail "missing PLAN-034a"
[[ -f "$GOLD/catalog.json" ]] && pass "catalog.json" || fail "missing catalog.json"
[[ -f "$GOLD/pharma-mqm.md" ]] && pass "pharma-mqm.md" || fail "missing pharma-mqm.md"
[[ -f "$GOLD/thresholds.toml" ]] && pass "thresholds.toml" || fail "missing thresholds.toml"
[[ -f "$GOLD/README.md" ]] && pass "gold README" || fail "missing gold README"
[[ -f "$ROOT/qyunslation/gold/plan034.py" ]] && pass "plan034.py" || fail "missing plan034.py"
[[ -f "$ROOT/scripts/plan034a-baseline.py" ]] && pass "baseline script" || fail "missing baseline"
[[ -f "$ROOT/scripts/plan034a-materialize-gold.py" ]] && pass "materialize script" || fail "missing materialize"
[[ -f "$ROOT/qyunslation/gold/synthesize.py" ]] && pass "synthesize module" || fail "missing synthesize"
[[ -f "$ROOT/docs/walkthroughs/WT-034a-gold-benchmark.md" ]] && pass "WT-034a" || fail "missing WT-034a"
grep -q 'plan034a-materialize-gold' "$ROOT/scripts/plan034a-materialize-gold.py" \
  && pass "materialize script id" || fail "materialize script id"

grep -q 'version: \*\*1.0.0\*\*' "$GOLD/pharma-mqm.md" \
  && pass "MQM version" || fail "MQM version"

run_pass "034a pytest" "$STAGE_DIR/t.log" \
  "$PY" -m pytest -q --no-cov \
    tests/gold/test_plan034a_catalog.py \
    tests/gold/test_plan034a1_materialize.py

# Sample completeness: incomplete → BLOCKED (not FAIL)
if "$PY" - <<'PY' >"$STAGE_DIR/complete.log" 2>&1
from qyunslation.gold.plan034 import CatalogCompletenessError, assert_catalog_complete
try:
    s = assert_catalog_complete()
    print("COMPLETE", s)
except CatalogCompletenessError as e:
    print("INCOMPLETE", e)
    raise SystemExit(2)
PY
then
  pass "gold root complete"
else
  blocked "gold root incomplete (need 10 ready+files per class L/C/R)"
  tail -n 20 "$STAGE_DIR/complete.log" || true
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

#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034e Translation Memory gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  PY="$ROOT/.venv/bin/python"
fi
STAGE_DIR="$(mktemp -d)"
FAILURES=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
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
  printf 'SUMMARY: FAIL fail=1\n'
  exit 1
fi

PLAN_E="$ROOT/docs/plans/PLAN-034-pharma-rd-mvp/PLAN-034e-translation-memory.md"
WT="$ROOT/docs/walkthroughs/WT-034e-translation-memory.md"

[[ -f "$PLAN_E" ]] && pass "PLAN-034e doc" || fail "missing PLAN-034e"
[[ -f "$WT" ]] && pass "WT-034e" || fail "missing WT-034e"
[[ -f "$ROOT/qyunslation/persist/tm_repo.py" ]] && pass "tm_repo" || fail "tm_repo"
[[ -f "$ROOT/qyunslation/tm/normalize.py" ]] && pass "normalize" || fail "normalize"
[[ -f "$ROOT/qyunslation/tm/match.py" ]] && pass "match" || fail "match"
[[ -f "$ROOT/qyunslation/tm/tmx.py" ]] && pass "tmx" || fail "tmx"
[[ -f "$ROOT/alembic/versions/034e0001_tm_unit.py" ]] \
  && pass "alembic 034e0001" || fail "alembic 034e0001"

grep -q 'tm_unit' "$PLAN_E" && pass "PLAN mentions tm_unit" || fail "PLAN tm_unit"
grep -q '001d4' "$PLAN_E" && pass "PLAN closes 001d4" || fail "001d4 note"
grep -q 'TmUnit' "$ROOT/qyunslation/persist/models.py" && pass "ORM TmUnit" || fail "ORM TmUnit"
grep -q '/tm/lookup' "$ROOT/qyunslation/api/v1.py" && pass "API lookup" || fail "API lookup"

run_pass "imports" "$STAGE_DIR/imp.log" \
  "$PY" -c "
from qyunslation.persist.models import TmUnit
from qyunslation.tm.normalize import normalize_source, placeholder_signature
from qyunslation.tm.match import exact_lookup, fuzzy_suggest
from qyunslation.tm.tmx import build_tmx, parse_tmx
assert normalize_source(' A  B ') == 'a b'
print('ok')
"

run_pass "034e pytest" "$STAGE_DIR/t.log" \
  "$PY" -m pytest -q --no-cov tests/persist/test_plan034e_tm.py

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s\n' "$FAILURES"
  exit 1
fi
printf 'SUMMARY: PASS fail=0\n'
exit 0

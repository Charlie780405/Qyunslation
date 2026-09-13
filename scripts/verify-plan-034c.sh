#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034c SaaS persistence gate. No live PG required for PASS.
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

PLAN_C="$ROOT/docs/plans/PLAN-034-pharma-rd-mvp/PLAN-034c-saas-persistence.md"
WT="$ROOT/docs/walkthroughs/WT-034c-saas-persistence.md"

[[ -f "$PLAN_C" ]] && pass "PLAN-034c doc" || fail "missing PLAN-034c"
[[ -f "$WT" ]] && pass "WT-034c" || fail "missing WT-034c"
[[ -f "$ROOT/qyunslation/persist/models.py" ]] && pass "persist models" || fail "persist models"
[[ -f "$ROOT/qyunslation/api/v1.py" ]] && pass "api v1" || fail "api v1"
[[ -f "$ROOT/alembic/versions/034c0001_initial_saas_tables.py" ]] \
  && pass "alembic revision" || fail "alembic revision"
[[ -f "$ROOT/docker-compose.plan034c.yml" ]] && pass "compose file" || fail "compose file"

grep -q 'QYUNSLATION_DATABASE_URL' "$WT" \
  && pass "WT documents DATABASE_URL" || fail "WT missing DATABASE_URL"
grep -q '无密钥' "$WT" || grep -q '勿' "$WT" \
  && pass "WT secret hygiene note" || fail "WT secret hygiene"

run_pass "imports" "$STAGE_DIR/imp.log" \
  "$PY" -c "
from qyunslation.persist.models import Tenant, Project, Job, AuditEvent, UserMembership
from qyunslation.api.v1 import router
from alembic.config import Config
Config('alembic.ini')
print('ok')
"

run_pass "034c pytest" "$STAGE_DIR/t.log" \
  "$PY" -m pytest -q --no-cov \
    tests/persist/test_plan034c_persist.py \
    tests/persist/test_plan034c_api.py

# Live alembic only when URL set; otherwise skip (not FAIL)
if [[ -n "${QYUNSLATION_DATABASE_URL:-}" ]]; then
  run_pass "alembic upgrade head" "$STAGE_DIR/al.log" \
    env QYUNSLATION_DATABASE_URL="$QYUNSLATION_DATABASE_URL" \
    "$PY" -m alembic -c alembic.ini upgrade head
else
  pass "alembic live skipped (no QYUNSLATION_DATABASE_URL)"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s\n' "$FAILURES"
  exit 1
fi
printf 'SUMMARY: PASS fail=0\n'
exit 0

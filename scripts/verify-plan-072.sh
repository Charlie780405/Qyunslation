#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-072：工作台持久化、断点续传与租户隔离验收。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
FAILURES=0
BLOCKED=0

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

REQUIRED=(
  "docs/plans/PLAN-072-durable-workbench-resume/README.md"
  "docs/plans/PLAN-072-durable-workbench-resume/PLAN-072a-preflight-form-restore.md"
  "docs/plans/PLAN-072-durable-workbench-resume/PLAN-072b-stage-resume-heartbeat.md"
  "docs/plans/PLAN-072-durable-workbench-resume/PLAN-072c-chunked-upload.md"
  "docs/plans/PLAN-072-durable-workbench-resume/PLAN-072d-review-draft.md"
  "docs/plans/PLAN-072-durable-workbench-resume/PLAN-072e-tenant-isolation-gc.md"
  "docs/walkthroughs/WT-072-durable-workbench-resume.md"
  "alembic/versions/072a0001_durable_workbench_resume.py"
  "qyunslation/workbench/heartbeat.py"
  "qyunslation/workbench/stage_persist.py"
  "frontend/src/next/stores/workbench.js"
  "scripts/plan072-gc-orphans.py"
)

for path in "${REQUIRED[@]}"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

grep -qE '@router\.get\("/preflights"\)|GET /api/v1/preflights' "$ROOT/qyunslation/api/v1.py" \
  && pass "list preflights endpoint" || fail "list preflights endpoint"
grep -q 'upload-sessions' "$ROOT/qyunslation/api/v1.py" \
  && pass "upload session endpoints" || fail "upload session endpoints"
grep -q 'review-draft' "$ROOT/qyunslation/api/v1.py" \
  && pass "review draft endpoints" || fail "review draft endpoints"
grep -q 'translation-runs/{run_id}/resume' "$ROOT/qyunslation/api/v1.py" \
  && pass "resume endpoint" || fail "resume endpoint"

if [[ -x "$PY" ]]; then
  if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= \
    tests/persist/test_plan072_migration.py \
    tests/api/test_plan072_resume.py) >"$ROOT/var/verify-plan-072-pytest.log" 2>&1; then
    pass "pytest plan072"
  else
    fail "pytest plan072 (see var/verify-plan-072-pytest.log)"
  fi
else
  blocked "pytest plan072 (venv python missing)"
fi

if [[ -d "$ROOT/frontend/node_modules" ]]; then
  if (cd "$ROOT/frontend" && npm test --silent) >"$ROOT/var/verify-plan-072-vitest.log" 2>&1; then
    pass "frontend vitest"
  else
    fail "frontend vitest (see var/verify-plan-072-vitest.log)"
  fi
else
  blocked "frontend vitest (node_modules missing)"
fi

if command -v chromium >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1; then
  blocked "browser refresh/resume evidence not captured in CI shell"
else
  blocked "browser refresh/resume evidence (no Chrome)"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  echo "SUMMARY: FAIL fail=$FAILURES blocked=$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  echo "SUMMARY: BLOCKED fail=0 blocked=$BLOCKED"
  exit 2
fi
echo "SUMMARY: PASS fail=0 blocked=0"
exit 0

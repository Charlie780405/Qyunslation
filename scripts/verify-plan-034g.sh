#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034g human review bench gate.
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

PLAN_G="$ROOT/docs/plans/PLAN-034-pharma-rd-mvp/PLAN-034g-human-review-bench.md"
WT="$ROOT/docs/walkthroughs/WT-034g-human-review-bench.md"

[[ -f "$PLAN_G" ]] && pass "PLAN-034g doc" || fail "missing PLAN-034g"
[[ -f "$WT" ]] && pass "WT-034g" || fail "missing WT-034g"
[[ -f "$ROOT/qyunslation/persist/review_repo.py" ]] && pass "review_repo" || fail "review_repo"
[[ -f "$ROOT/alembic/versions/034g0001_review_bench.py" ]] \
  && pass "alembic 034g0001" || fail "alembic 034g0001"
[[ -f "$ROOT/qyunslation/static/review.html" ]] && pass "review.html" || fail "review.html"

grep -q 'HUMAN_REVIEW' "$PLAN_G" && pass "PLAN HUMAN_REVIEW" || fail "PLAN HUMAN_REVIEW"
grep -q 'DevBypass\|DEV_AUTH\|旁路' "$WT" && pass "WT auth note" || fail "WT auth note"
grep -q '/review/enqueue' "$ROOT/qyunslation/api/v1.py" && pass "API enqueue" || fail "API enqueue"
grep -q 'ReviewSegment' "$ROOT/qyunslation/persist/models.py" && pass "ORM ReviewSegment" || fail "ORM"

run_pass "imports" "$STAGE_DIR/imp.log" \
  "$PY" -c "
from qyunslation.persist.models import ReviewSegment, ReviewNote, ReviewRevision
from qyunslation.persist.review_repo import should_enqueue
assert should_enqueue('HUMAN_REVIEW') and not should_enqueue('PRESERVE')
print('ok')
"

run_pass "034g pytest" "$STAGE_DIR/t.log" \
  "$PY" -m pytest -q --no-cov tests/persist/test_plan034g_review.py

run_pass "static page markers" "$STAGE_DIR/html.log" \
  "$PY" -c "
from pathlib import Path
html = Path('qyunslation/static/review.html').read_text(encoding='utf-8')
assert 'X-Dev-User' in html and '批准' in html and '/api/v1/review/' in html
print('ok')
"

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s\n' "$FAILURES"
  exit 1
fi
printf 'SUMMARY: PASS fail=0\n'
exit 0

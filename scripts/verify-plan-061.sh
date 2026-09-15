#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-061：术语工作台可用性修复三态门禁。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  COMMON_GIT_DIR="$(git -C "$ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
  COMMON_ROOT="$(cd "$(dirname "${COMMON_GIT_DIR:-/nonexistent}")" 2>/dev/null && pwd || true)"
  [[ -x "${COMMON_ROOT:-}/.venv/bin/python" ]] && PY="$COMMON_ROOT/.venv/bin/python"
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
  fail "Python interpreter unavailable; set QYUNSLATION_VERIFY_PY"
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-061-termbase-workbench-fix"
WT="$ROOT/docs/walkthroughs/WT-061-termbase-workbench-fix.md"
for required in \
  "$PLAN_DIR/README.md" \
  "$PLAN_DIR/PLAN-061a-save-path-diagnosability.md" \
  "$PLAN_DIR/PLAN-061b-candidate-admission-rules.md" \
  "$PLAN_DIR/PLAN-061c-observed-and-suggested-target.md" \
  "$PLAN_DIR/PLAN-061d-verification-delivery.md" \
  "$WT" \
  "$ROOT/glossaries/term-candidate-rules.toml" \
  "$ROOT/qyunslation/glossary/candidate_rules.py" \
  "$ROOT/qyunslation/workbench/term_align.py" \
  "$ROOT/qyunslation/workbench/bridge.py" \
  "$ROOT/qyunslation/workbench/gui_client.py" \
  "$ROOT/scripts/apply-pdf2zh-060-termbase-workbench.py"; do
  [[ -f "$required" ]] && pass "static $(basename "$required")" || fail "missing $required"
done

grep -q 'PLAN-061-termbase-workbench-fix' "$ROOT/docs/plans/README.md" \
  && pass "plans index PLAN-061" || fail "plans index missing PLAN-061"
if grep -q 'QYUNSLATION_TERM_BRIDGE_SECRET' "$ROOT/scripts/apply-pdf2zh-060-termbase-workbench.py"; then
  fail "GUI patch must not expose bridge secret"
else
  pass "GUI patch contains no bridge secret"
fi
grep -q 'chosen_target = (table_target or "").strip() or (target or "").strip()' \
  "$ROOT/scripts/apply-pdf2zh-060-termbase-workbench.py" \
  && pass "save path prefers filled confirmation" || fail "save path still prefers empty table cell"

if "$PY" -m compileall -q \
  qyunslation/workbench \
  qyunslation/glossary/candidate_rules.py \
  scripts/apply-pdf2zh-060-termbase-workbench.py; then
  pass "PLAN-061 modules compile"
else
  fail "PLAN-061 modules compile"
fi

if "$PY" -m pytest -q --no-cov \
  tests/workbench/test_plan061_candidate_rules.py \
  tests/workbench/test_plan061_term_align.py \
  tests/workbench/test_plan061_gui_client_errors.py \
  tests/ui/test_plan061_workbench_patch.py \
  tests/workbench/test_plan060_evidence.py \
  tests/workbench/test_plan060_bridge.py \
  tests/ui/test_plan060_workbench_patch.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "PLAN-061 focused pytest"
else
  fail "PLAN-061 focused pytest"
  tail -n 80 "$STAGE_DIR/pytest.log" || true
fi

if [[ "${QYUNSLATION_PLAN061_LIVE:-}" == "1" || "${QYUNSLATION_PLAN061_LIVE:-}" == "true" ]]; then
  if "$PY" - <<'PY'
from qyunslation.gateway.provider import ping_provider
print(ping_provider())
raise SystemExit(0 if ping_provider().get("ok") else 2)
PY
  then
    pass "LIVE provider ping"
  else
    blocked "LIVE provider ping unavailable"
  fi
  if [[ -z "${QYUNSLATION_DATABASE_URL:-}" ]]; then
    blocked "QYUNSLATION_DATABASE_URL is unset"
  elif "$PY" -m alembic upgrade head >"$STAGE_DIR/alembic.log" 2>&1; then
    pass "LIVE alembic upgrade"
  else
    blocked "LIVE alembic upgrade unavailable"
    tail -n 40 "$STAGE_DIR/alembic.log" || true
  fi
  if [[ -z "${QYUNSLATION_PLAN061_BROWSER_EVIDENCE:-}" || ! -f "${QYUNSLATION_PLAN061_BROWSER_EVIDENCE:-}" ]]; then
    blocked "browser five-check evidence is missing"
  else
    pass "browser five-check evidence supplied"
  fi
else
  pass "LIVE deployment checks skipped (set QYUNSLATION_PLAN061_LIVE=1)"
fi

if [[ "${QYUNSLATION_PLAN061_FULL:-}" == "1" || "${QYUNSLATION_PLAN061_FULL:-}" == "true" ]]; then
  for gate in 060 058; do
    log="$STAGE_DIR/dependency-$gate.log"
    if QYUNSLATION_VERIFY_PY="$PY" bash "$ROOT/scripts/verify-plan-$gate.sh" >"$log" 2>&1; then
      pass "dependency gate PLAN-$gate"
    else
      code=$?
      if [[ "$code" -eq 2 ]] || grep -q '^SUMMARY: BLOCKED' "$log"; then
        blocked "dependency gate PLAN-$gate"
      else
        fail "dependency gate PLAN-$gate"
      fi
      tail -n 35 "$log" || true
    fi
  done
else
  pass "dependency gates skipped (set QYUNSLATION_PLAN061_FULL=1)"
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

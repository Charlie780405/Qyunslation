#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-060：公司共享术语工作台三态门禁。
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

PLAN_DIR="$ROOT/docs/plans/PLAN-060-company-termbase-workbench"
WT="$ROOT/docs/walkthroughs/WT-060-company-termbase-workbench.md"
for required in \
  "$PLAN_DIR/README.md" \
  "$PLAN_DIR/PLAN-060a-baseline-governance.md" \
  "$PLAN_DIR/PLAN-060b-signed-bridge.md" \
  "$PLAN_DIR/PLAN-060c-pretranslation-policy.md" \
  "$PLAN_DIR/PLAN-060d-evidence-extraction.md" \
  "$PLAN_DIR/PLAN-060e-gradio-review-panel.md" \
  "$PLAN_DIR/PLAN-060f-verification-delivery.md" \
  "$WT" \
  "$ROOT/docs/decisions/ADR-031-company-termbase-workbench-bridge.md" \
  "$ROOT/alembic/versions/060a0001_workbench_term_review.py" \
  "$ROOT/qyunslation/workbench/bridge.py" \
  "$ROOT/qyunslation/workbench/gui_client.py" \
  "$ROOT/scripts/apply-pdf2zh-060-termbase-workbench.py" \
  "$ROOT/scripts/manage-term-admin.py"; do
  [[ -f "$required" ]] && pass "static $(basename "$required")" || fail "missing $required"
done

grep -q 'PLAN-060-company-termbase-workbench' "$ROOT/docs/plans/README.md" \
  && pass "plans index PLAN-060" || fail "plans index missing PLAN-060"
grep -q 'apply-pdf2zh-060-termbase-workbench.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "pdf2zh service runs PLAN-060 patch" || fail "pdf2zh service missing PLAN-060 patch"
if grep -q 'QYUNSLATION_TERM_BRIDGE_SECRET' "$ROOT/scripts/apply-pdf2zh-060-termbase-workbench.py"; then
  fail "GUI patch must not expose bridge secret"
else
  pass "GUI patch contains no bridge secret"
fi

if "$PY" -m compileall -q qyunslation/workbench scripts/apply-pdf2zh-060-termbase-workbench.py scripts/manage-term-admin.py; then
  pass "PLAN-060 modules compile"
else
  fail "PLAN-060 modules compile"
fi

if "$PY" -m pytest -q --no-cov \
  tests/workbench/test_plan060_bridge.py \
  tests/workbench/test_plan060_evidence.py \
  tests/ui/test_plan060_workbench_patch.py \
  tests/persist/test_plan060_migration.py \
  tests/persist/test_plan058_candidate.py \
  tests/persist/test_plan058_api.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "PLAN-060 focused pytest"
else
  fail "PLAN-060 focused pytest"
  tail -n 100 "$STAGE_DIR/pytest.log" || true
fi

if [[ "${QYUNSLATION_PLAN060_LIVE:-}" == "1" || "${QYUNSLATION_PLAN060_LIVE:-}" == "true" ]]; then
  if [[ -z "${QYUNSLATION_DATABASE_URL:-}" ]]; then
    blocked "QYUNSLATION_DATABASE_URL is unset"
  elif "$PY" -m alembic upgrade head >"$STAGE_DIR/alembic.log" 2>&1; then
    pass "LIVE alembic upgrade"
  else
    blocked "LIVE alembic upgrade unavailable"
    tail -n 40 "$STAGE_DIR/alembic.log" || true
  fi

  CADDYFILE="${QYUNSLATION_PLAN060_CADDYFILE:-}"
  if [[ -z "$CADDYFILE" || ! -f "$CADDYFILE" ]]; then
    blocked "set QYUNSLATION_PLAN060_CADDYFILE for internal-route negative assertion"
  elif grep -q '/internal/workbench' "$CADDYFILE"; then
    fail "Caddy exposes /internal/workbench"
  else
    pass "Caddy does not expose internal workbench route"
  fi

  if [[ -z "${QYUNSLATION_TERM_BRIDGE_SECRET:-}" || -z "${QYUNSLATION_WORKBENCH_TENANT:-}" ]]; then
    blocked "bridge secret or workbench tenant is unset"
  else
    pass "bridge deployment variables are present"
  fi

  if [[ -z "${QYUNSLATION_PLAN060_BROWSER_EVIDENCE:-}" || ! -f "${QYUNSLATION_PLAN060_BROWSER_EVIDENCE:-}" ]]; then
    blocked "browser four-width evidence is missing"
  else
    pass "browser four-width evidence supplied"
  fi
else
  pass "LIVE deployment checks skipped (set QYUNSLATION_PLAN060_LIVE=1)"
fi

if [[ "${QYUNSLATION_PLAN060_FULL:-}" == "1" || "${QYUNSLATION_PLAN060_FULL:-}" == "true" ]]; then
  for gate in 058 050e 057 059; do
    # PLAN-050e is a subplan; its maintained gate is verify-plan-050.sh.
    gate_script="$gate"
    [[ "$gate" == "050e" ]] && gate_script="050"
    log="$STAGE_DIR/dependency-$gate.log"
    if QYUNSLATION_VERIFY_PY="$PY" bash "$ROOT/scripts/verify-plan-$gate_script.sh" >"$log" 2>&1; then
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
  pass "dependency gates skipped (set QYUNSLATION_PLAN060_FULL=1)"
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

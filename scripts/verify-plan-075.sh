#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-075：073/074 收口总验收。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
FAILURES=0
BLOCKED=0

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

REQUIRED=(
  "docs/plans/PLAN-075-073-074-closeout/README.md"
  "docs/plans/PLAN-074-author-terms-qa/README.md"
  "docs/walkthroughs/WT-074-author-terms-qa.md"
  "docs/walkthroughs/WT-075-073-074-closeout.md"
  "scripts/deploy_gate.py"
  "scripts/plan074-live-regression.py"
  "scripts/plan073-import-domain-autoimmune.py"
  "tests/gold/autoimmune/shared_required_terms.json"
)
for path in "${REQUIRED[@]}"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

if [[ -x "$PY" ]]; then
  if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= \
    tests/scripts/test_deploy_gate.py \
    tests/api/test_plan075_egress_audit.py); then
    pass "075b/075d gate and egress tests"
  else
    fail "075b/075d gate and egress tests"
  fi

  gate_rc=0
  OFFICE_ENV="${QYUNSLATION_OFFICE_ENV:-/home/dev/pdf2zh/office.env}"
  if [[ -f "$OFFICE_ENV" ]]; then
    export QYUNSLATION_DATABASE_URL="$(grep -E '^QYUNSLATION_DATABASE_URL=' "$OFFICE_ENV" | cut -d= -f2- | tr -d '"' | tr -d "'")"
  fi
  (cd "$ROOT" && "$PY" scripts/deploy_gate.py report >/dev/null) || gate_rc=$?
  if [[ "$gate_rc" -eq 0 ]]; then
    pass "deploy gate report (migration aligned)"
  else
    blocked "deploy gate report not fully aligned (check migration/frontend)"
  fi

  import_rc=0
  (cd "$ROOT" && "$PY" scripts/plan073-import-domain-autoimmune.py --dry-run) || import_rc=$?
  if [[ "$import_rc" -eq 0 ]]; then
    pass "domain-autoimmune import dry-run"
  else
    fail "domain-autoimmune import dry-run"
  fi
else
  fail "Python interpreter unavailable"
fi

if bash "$ROOT/scripts/verify-plan-074.sh" >/tmp/verify-plan-075-074.log 2>&1; then
  pass "verify-plan-074 aggregate"
elif [[ "$?" -eq 2 ]]; then
  blocked "verify-plan-074 blocked (see /tmp/verify-plan-075-074.log)"
else
  # verify-plan-074 exits 1 on fail, 2 on blocked-only
  if grep -q 'SUMMARY: BLOCKED' /tmp/verify-plan-075-074.log && ! grep -q 'SUMMARY: FAIL' /tmp/verify-plan-075-074.log; then
    blocked "verify-plan-074 blocked-only"
  else
    fail "verify-plan-074 (see /tmp/verify-plan-075-074.log)"
  fi
fi

if bash "$ROOT/scripts/verify-plan-073.sh" >/tmp/verify-plan-075-073.log 2>&1; then
  pass "verify-plan-073 aggregate"
else
  rc=$?
  if [[ "$rc" -eq 2 ]] || grep -q 'SUMMARY: BLOCKED' /tmp/verify-plan-075-073.log; then
    blocked "verify-plan-073 blocked items remain (DeepSeek/browser/domain eval)"
  else
    fail "verify-plan-073 (see /tmp/verify-plan-075-073.log)"
  fi
fi

OFFICE_ENV="${QYUNSLATION_OFFICE_ENV:-/home/dev/pdf2zh/office.env}"
if grep -qE '^QYUNSLATION_DEEPSEEK_API_KEY=.+' "$OFFICE_ENV" 2>/dev/null; then
  pass "deepseek key configured"
  if [[ -x "$PY" ]]; then
    if (cd "$ROOT" && set -a && source <(grep -E '^QYUNSLATION_DEEPSEEK_API_KEY=' "$OFFICE_ENV" | sed 's/^/export /') && set +a && \
      "$PY" -c "from qyunslation.pipeline.model_profiles import deepseek_configured; import sys; sys.exit(0 if deepseek_configured() else 1)"); then
      pass "deepseek runtime profile available"
    else
      blocked "deepseek key present but runtime profile unavailable"
    fi
  fi
else
  blocked "deepseek key not configured in office.env"
fi

if command -v chromium >/dev/null 2>&1; then
  pass "headless chromium available"
else
  blocked "chromium not in PATH (run scripts/install-headless-chromium.sh)"
fi

if compgen -G "$ROOT/docs/evidence/plan073-074/*.png" >/dev/null; then
  pass "browser evidence screenshots"
else
  blocked "browser evidence PNG missing under docs/evidence/plan073-074/"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED fail=0 blocked=%s\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
exit 0

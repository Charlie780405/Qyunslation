#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034h SaaS pilot gate (OIDC/PWA/checklist/smoke/catalog).
# Does NOT call verify-plan-034.sh (umbrella already runs a–g then this).
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

PLAN_H="$ROOT/docs/plans/PLAN-034-pharma-rd-mvp/PLAN-034h-gold-saas-pilot.md"
WT_H="$ROOT/docs/walkthroughs/WT-034h-gold-saas-pilot.md"
WT_034="$ROOT/docs/walkthroughs/WT-034-pharma-rd-mvp.md"

[[ -f "$PLAN_H" ]] && pass "PLAN-034h doc" || fail "missing PLAN-034h"
[[ -f "$WT_H" ]] && pass "WT-034h" || fail "missing WT-034h"
[[ -f "$WT_034" ]] && pass "WT-034" || fail "missing WT-034"
[[ -f "$ROOT/qyunslation/static/manifest.webmanifest" ]] && pass "PWA manifest" || fail "PWA manifest"
[[ -f "$ROOT/qyunslation/static/sw-034h.js" ]] && pass "PWA sw" || fail "PWA sw"
[[ -f "$ROOT/scripts/plan034h-release-checklist.sh" ]] && pass "release checklist" || fail "checklist"
grep -q 'OidcAdapter' "$ROOT/qyunslation/persist/identity.py" \
  && grep -q 'PyJWKClient\|jwt.decode' "$ROOT/qyunslation/persist/identity.py" \
  && pass "OIDC JWT code" || fail "OIDC JWT code"
grep -q 'PyJWT' "$ROOT/pyproject.toml" && pass "PyJWT dep" || fail "PyJWT dep"
# 伞门必须串本门（本门不反向递归调用伞门）
grep -q 'verify-plan-034h.sh' "$ROOT/scripts/verify-plan-034.sh" \
  && pass "umbrella chains 034h" || fail "umbrella missing 034h"
grep -q 'FAIL/BLOCKED\|不得宣称' "$WT_034" && pass "WT-034 completion rule" || fail "WT-034 rule"

# 合并前硬门：034c–034g 迁移链必须线性单 head，否则 migrate deploy 会 multiple heads
run_pass "alembic single head" "$STAGE_DIR/heads.log" \
  "$PY" -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
sd = ScriptDirectory.from_config(Config('alembic.ini'))
heads = sd.get_heads()
assert len(heads) == 1, f'multiple heads: {heads}'
revs = [r.revision for r in sd.walk_revisions()]
for need in ('034c0001', '034d0001', '034e0001', '034f0001', '034g0001'):
    assert need in revs, f'missing revision {need}'
print('head', heads[0])
"

run_pass "OIDC pytest" "$STAGE_DIR/oidc.log" \
  "$PY" -m pytest -q --no-cov tests/persist/test_plan034h_oidc.py

run_pass "SaaS smoke pytest" "$STAGE_DIR/smoke.log" \
  "$PY" -m pytest -q --no-cov tests/persist/test_plan034h_saas_smoke.py

run_pass "release checklist dry" "$STAGE_DIR/chk.log" \
  bash "$ROOT/scripts/plan034h-release-checklist.sh"

run_pass "PWA markers" "$STAGE_DIR/pwa.log" \
  "$PY" -c "
from pathlib import Path
m = Path('qyunslation/static/manifest.webmanifest').read_text(encoding='utf-8')
assert 'review.html' in m and 'standalone' in m
r = Path('qyunslation/static/review.html').read_text(encoding='utf-8')
assert 'manifest.webmanifest' in r and 'sw-034h.js' in r
i = Path('qyunslation/static/index.html').read_text(encoding='utf-8')
assert 'manifest.webmanifest' in i and 'sw-034h.js' in i
print('ok')
"

# Gold catalog completeness → BLOCKED if incomplete
if "$PY" -c "
from qyunslation.gold.plan034 import CatalogCompletenessError, assert_catalog_complete
try:
    r = assert_catalog_complete()
    print(r)
except CatalogCompletenessError as e:
    print('INCOMPLETE', e.reasons)
    raise SystemExit(2)
except Exception as e:
    print('ERROR', e)
    raise SystemExit(1)
" >"$STAGE_DIR/gold.log" 2>&1; then
  pass "gold catalog complete"
else
  code=$?
  if [[ "$code" -eq 2 ]]; then
    blocked "gold catalog incomplete"
  else
    fail "gold catalog check error"
  fi
  tail -n 20 "$STAGE_DIR/gold.log" || true
fi

# Optional full gold E2E
if [[ "${QYUNSLATION_PLAN034_GOLD_E2E:-}" == "1" ]]; then
  if "$PY" -c "
from qyunslation.gold.plan034 import evaluate_baseline_report, load_thresholds
th = load_thresholds()
# 实跑报告需本机 GOLD_ROOT；此处要求调用方提供 QYUNSLATION_PLAN034_GOLD_REPORT
import json, os
path = os.environ.get('QYUNSLATION_PLAN034_GOLD_REPORT')
if not path:
    raise SystemExit(2)
rep = json.loads(open(path, encoding='utf-8').read())
assert evaluate_baseline_report(rep, th) == 'pass'
print('ok')
" >"$STAGE_DIR/e2e.log" 2>&1; then
    pass "gold e2e baseline"
  else
    blocked "gold e2e failed or report missing"
    tail -n 20 "$STAGE_DIR/e2e.log" || true
  fi
else
  blocked "gold e2e not enabled (set QYUNSLATION_PLAN034_GOLD_E2E=1)"
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

#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034f model gateway + deterministic QA gate.
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
# 本机 .env 含 DOCUTRANSLATE_BASE_URL / QYUNSLATION_BASE_URL；不打印内容
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

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
  printf 'SUMMARY: FAIL fail=1\n'
  exit 1
fi

PLAN_F="$ROOT/docs/plans/PLAN-034-pharma-rd-mvp/PLAN-034f-model-gateway-qa.md"
WT="$ROOT/docs/walkthroughs/WT-034f-model-gateway-qa.md"

[[ -f "$PLAN_F" ]] && pass "PLAN-034f doc" || fail "missing PLAN-034f"
[[ -f "$WT" ]] && pass "WT-034f" || fail "missing WT-034f"
[[ -f "$ROOT/qyunslation/gateway/profiles.yaml" ]] && pass "profiles.yaml" || fail "profiles.yaml"
[[ -f "$ROOT/qyunslation/gateway/config.py" ]] && pass "gateway config" || fail "gateway config"
[[ -f "$ROOT/qyunslation/gateway/provider.py" ]] && pass "provider" || fail "provider"
[[ -f "$ROOT/qyunslation/gateway/qa.py" ]] && pass "qa" || fail "qa"
[[ -f "$ROOT/qyunslation/gateway/pipeline.py" ]] && pass "pipeline" || fail "pipeline"
[[ -f "$ROOT/alembic/versions/034f0001_job_provenance.py" ]] \
  && pass "alembic 034f0001" || fail "alembic 034f0001"
[[ -f "$ROOT/scripts/plan034f-sync-pdf2zh-model.py" ]] && pass "pdf2zh sync script" || fail "sync script"

grep -q 'qwen3.6:35b-a3b' "$ROOT/qyunslation/gateway/profiles.yaml" \
  && pass "baseline model in profiles" || fail "baseline model"
grep -q 'TranslatorProvider\|QwenOllama' "$PLAN_F" && pass "PLAN mentions provider" || fail "PLAN provider"
grep -q '/qa/run' "$ROOT/qyunslation/api/v1.py" && pass "API qa/run" || fail "API qa/run"
grep -q 'provenance' "$ROOT/qyunslation/persist/models.py" && pass "Job.provenance" || fail "Job.provenance"

run_pass "imports" "$STAGE_DIR/imp.log" \
  "$PY" -c "
from qyunslation.gateway.config import BASELINE_MODEL_ID, resolve_profile
from qyunslation.gateway.qa import CHECKLIST
assert resolve_profile('quality')['model_id'] == BASELINE_MODEL_ID
assert len(CHECKLIST) == 12
print('ok')
"

run_pass "034f pytest" "$STAGE_DIR/t.log" \
  "$PY" -m pytest -q --no-cov tests/gateway/test_plan034f_gateway.py

run_pass "sync script dry" "$STAGE_DIR/sync.log" \
  "$PY" "$ROOT/scripts/plan034f-sync-pdf2zh-model.py"

# 泰州 Ollama 可达性：失败记 BLOCKED 不记 FAIL
if "$PY" -c "
from qyunslation.gateway.provider import ping_provider
r = ping_provider(profile='quality')
print(r)
raise SystemExit(0 if r.get('ok') else 2)
" >"$STAGE_DIR/ping.log" 2>&1; then
  pass "ollama ping"
else
  blocked "ollama ping (unreachable or no endpoint)"
  tail -n 5 "$STAGE_DIR/ping.log" || true
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

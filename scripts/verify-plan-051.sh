#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-051：金标整本 Pharma-MQM 门（默认不烧 GPU；LIVE 才整本）。
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

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL fail=1 blocked=0\n'
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-051-gold-pharma-mqm"
WT="$ROOT/docs/walkthroughs/WT-051-gold-pharma-mqm.md"

[[ -f "$PLAN_DIR/PLAN-051-gold-pharma-mqm.md" ]] && pass "PLAN-051 charter" || fail "PLAN-051 charter"
[[ -f "$PLAN_DIR/PLAN-051a-gold-runner.md" ]] && pass "PLAN-051a" || fail "PLAN-051a"
[[ -f "$PLAN_DIR/PLAN-051b-mqm-scorer.md" ]] && pass "PLAN-051b" || fail "PLAN-051b"
[[ -f "$PLAN_DIR/PLAN-051c-verify-gate.md" ]] && pass "PLAN-051c" || fail "PLAN-051c"
[[ -f "$WT" ]] && pass "WT-051" || fail "WT-051"
[[ -f "$ROOT/scripts/plan051-run-gold.py" ]] && pass "run-gold script" || fail "run-gold script"
[[ -f "$ROOT/scripts/plan051-score-gold.py" ]] && pass "score-gold script" || fail "score-gold script"
[[ -f "$ROOT/qyunslation/gold/plan051_run.py" ]] && pass "plan051_run module" || fail "plan051_run module"
[[ -f "$ROOT/qyunslation/gold/plan051_score.py" ]] && pass "plan051_score module" || fail "plan051_score module"

if "$PY" -m pytest -q --no-cov \
  tests/gold/test_plan051a_run.py \
  tests/gold/test_plan051b_score.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "plan051 pytest"
else
  fail "plan051 pytest"
  tail -n 40 "$STAGE_DIR/pytest.log" || true
fi

# 拒 skeleton
cat >"$STAGE_DIR/skeleton.json" <<'EOF'
{
  "mode": "catalog-skeleton",
  "critical_count": 0,
  "hard_term_hit_rate": 1.0,
  "forbidden_translation_count": 0,
  "digit_unit_doi_ref_pass_rate": 1.0
}
EOF
if "$PY" "$ROOT/scripts/plan051-score-gold.py" --reject-if "$STAGE_DIR/skeleton.json" \
  >"$STAGE_DIR/reject.log" 2>&1; then
  fail "scorer should reject skeleton"
  cat "$STAGE_DIR/reject.log" || true
else
  pass "scorer rejects skeleton"
fi

LIVE="${QYUNSLATION_PLAN051_LIVE:-}"
if [[ "$LIVE" == "1" || "$LIVE" == "true" ]]; then
  # catalog
  if "$PY" -c "
from qyunslation.gold.plan034 import assert_catalog_complete, CatalogCompletenessError
try:
    print(assert_catalog_complete())
except CatalogCompletenessError as e:
    raise SystemExit(2) from e
" >"$STAGE_DIR/catalog.log" 2>&1; then
    pass "LIVE catalog complete"
  else
    code=$?
    if [[ "$code" -eq 2 ]]; then
      blocked "LIVE catalog incomplete"
    else
      fail "LIVE catalog check"
    fi
    tail -n 20 "$STAGE_DIR/catalog.log" || true
  fi

  # Ollama probe
  HOST="${QYUNSLATION_OLLAMA_HOST:-http://100.67.66.123:11434}"
  if curl -sf -m 5 "${HOST%/}/api/tags" >"$STAGE_DIR/ollama.json" 2>/dev/null; then
    pass "LIVE ollama reachable"
  else
    blocked "LIVE ollama unreachable"
  fi

  if [[ "$BLOCKED" -eq 0 && "$FAILURES" -eq 0 ]]; then
    LIMIT_ARGS=()
    if [[ -n "${QYUNSLATION_PLAN051_LIMIT:-}" ]]; then
      LIMIT_ARGS=(--limit "${QYUNSLATION_PLAN051_LIMIT}")
    fi
    if "$PY" "$ROOT/scripts/plan051-run-gold.py" "${LIMIT_ARGS[@]}" \
      --json-out "$STAGE_DIR/runs.json" >"$STAGE_DIR/run.log" 2>&1; then
      pass "LIVE run-gold"
    else
      code=$?
      if [[ "$code" -eq 2 ]]; then
        blocked "LIVE run-gold blocked"
      else
        fail "LIVE run-gold"
      fi
      tail -n 30 "$STAGE_DIR/run.log" || true
    fi

    if [[ "$BLOCKED" -eq 0 && "$FAILURES" -eq 0 ]]; then
      if "$PY" "$ROOT/scripts/plan051-score-gold.py" \
        --json-out "$STAGE_DIR/mqm.json" >"$STAGE_DIR/score.log" 2>&1; then
        pass "LIVE score evaluate"
      else
        fail "LIVE score evaluate (quality)"
        tail -n 30 "$STAGE_DIR/score.log" || true
      fi

      # 产品门：R 类真件
      if "$PY" -c "
import json,sys
from qyunslation.gold.plan034 import load_catalog
real_r=sum(1 for e in load_catalog() if e.status=='ready' and e.class_=='R' and 'real' in e.tags)
print('real_R', real_r)
raise SystemExit(0 if real_r>0 else 2)
" >"$STAGE_DIR/product.log" 2>&1; then
        pass "LIVE product-line R has real gold"
        printf 'engineering=PASS\nproduct=PASS\n'
      else
        blocked "product-line R has no real gold"
        printf 'engineering=PASS\nproduct=BLOCKED\n'
        tail -n 5 "$STAGE_DIR/product.log" || true
      fi
    fi
  fi
else
  pass "LIVE skipped (set QYUNSLATION_PLAN051_LIVE=1 to run full retranslate)"
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

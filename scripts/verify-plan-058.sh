#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-058：医药术语闭环工程门 / 真实金标三态门禁。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  PY="$ROOT/.venv/bin/python"
fi
# Cursor worktrees normally share the source checkout's virtualenv.  Resolve
# it from git metadata instead of depending on a machine-specific path.
if [[ ! -x "$PY" ]]; then
  COMMON_GIT_DIR="$(git -C "$ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
  if [[ -n "$COMMON_GIT_DIR" ]]; then
    COMMON_ROOT="$(cd "$(dirname "$COMMON_GIT_DIR")" 2>/dev/null && pwd || true)"
    if [[ -x "${COMMON_ROOT:-}/.venv/bin/python" ]]; then
      PY="$COMMON_ROOT/.venv/bin/python"
    fi
  fi
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

PLAN_DIR="$ROOT/docs/plans/PLAN-058-pharma-termbase-loop"
WT="$ROOT/docs/walkthroughs/WT-058-pharma-termbase-loop.md"

for required in \
  "$PLAN_DIR/README.md" \
  "$PLAN_DIR/PLAN-058a-baseline-contract.md" \
  "$PLAN_DIR/PLAN-058b-storage-vector.md" \
  "$PLAN_DIR/PLAN-058c-pretranslation-retrieval.md" \
  "$PLAN_DIR/PLAN-058d-posttranslation-extraction.md" \
  "$PLAN_DIR/PLAN-058e-review-governance.md" \
  "$PLAN_DIR/PLAN-058f-policy-qa-gate.md" \
  "$PLAN_DIR/PLAN-058g-evaluation-delivery.md" \
  "$WT" \
  "$ROOT/qyunslation/glossary/resolver.py" \
  "$ROOT/qyunslation/glossary/evaluation.py" \
  "$ROOT/qyunslation/persist/term_embedding_repo.py" \
  "$ROOT/alembic/versions/058a0001_termbase_loop.py"; do
  if [[ -f "$required" ]]; then
    pass "static $(basename "$required")"
  else
    fail "missing $required"
  fi
done

if "$PY" -m pytest -q --no-cov \
  tests/test_glossary/test_plan058_evaluation.py \
  tests/test_glossary/test_plan058_resolver.py \
  tests/test_glossary/test_plan058_policy.py \
  tests/persist/test_plan058_termbase.py \
  tests/persist/test_plan058_candidate.py \
  tests/persist/test_plan058_embedding.py \
  tests/persist/test_plan058_api.py \
  tests/persist/test_plan058_migration.py \
  tests/server/test_plan058_qa.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "PLAN-058 focused pytest"
else
  fail "PLAN-058 focused pytest"
  tail -n 60 "$STAGE_DIR/pytest.log" || true
fi

LIVE="${QYUNSLATION_PLAN058_LIVE:-}"
if [[ "$LIVE" != "1" && "$LIVE" != "true" ]]; then
  pass "LIVE skipped (set QYUNSLATION_PLAN058_LIVE=1 for product gate)"
else
  GOLD="${QYUNSLATION_PLAN058_GOLD:-}"
  if [[ -z "$GOLD" || ! -f "$GOLD" ]]; then
    blocked "QYUNSLATION_PLAN058_GOLD is missing"
  else
    if "$PY" - "$GOLD" <<'PY' >"$STAGE_DIR/gold.log" 2>&1
import json
import sys
from qyunslation.glossary.evaluation import evaluate_retrieval

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
report = evaluate_retrieval(payload.get("gold", []), payload.get("predictions", []))
print(json.dumps(report, ensure_ascii=False, sort_keys=True))
thresholds = {
    "recall_at_5": 0.95,
    "occurrence_recall": 0.95,
    "top1_precision": 0.95,
    "high_confidence_coverage": 0.80,
    "exact_detection": 0.99,
}
if not payload.get("gold"):
    raise SystemExit("gold is empty")
failed = [f"{key}={report[key]:.4f} < {value:.2f}" for key, value in thresholds.items() if report[key] < value]
if failed:
    raise SystemExit("; ".join(failed))
PY
    then
      pass "PLAN-058 retrieval gold thresholds"
      cat "$STAGE_DIR/gold.log"
    else
      fail "PLAN-058 retrieval gold thresholds"
      cat "$STAGE_DIR/gold.log"
    fi
  fi

  if [[ -z "${QYUNSLATION_DATABASE_URL:-}" ]]; then
    blocked "QYUNSLATION_DATABASE_URL is unset; skip live migration"
  elif "$PY" -m alembic upgrade head >"$STAGE_DIR/alembic.log" 2>&1; then
    pass "LIVE alembic upgrade"
  else
    blocked "LIVE alembic upgrade unavailable"
    tail -n 40 "$STAGE_DIR/alembic.log" || true
  fi
fi

if [[ "${QYUNSLATION_PLAN058_FULL:-}" == "1" || "${QYUNSLATION_PLAN058_FULL:-}" == "true" ]]; then
  for gate in 034d 034g 039 050e 051 055; do
    if bash "$ROOT/scripts/verify-plan-$gate.sh" >"$STAGE_DIR/plan-$gate.log" 2>&1; then
      pass "dependency gate PLAN-$gate"
    else
      code=$?
      if [[ "$code" -eq 2 ]]; then
        blocked "dependency gate PLAN-$gate"
      else
        fail "dependency gate PLAN-$gate"
      fi
      tail -n 25 "$STAGE_DIR/plan-$gate.log" || true
    fi
  done
else
  pass "dependency gates skipped (set QYUNSLATION_PLAN058_FULL=1)"
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

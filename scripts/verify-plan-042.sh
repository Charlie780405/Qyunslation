#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-042 regulatory translation quality gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"
  elif [[ -x /home/dev/qyunslation/.venv/bin/python ]]; then
    PY=/home/dev/qyunslation/.venv/bin/python
  else
    PY="$ROOT/.venv/bin/python"
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

run_pass() {
  local label="$1" log="$2"
  shift 2
  if "$@" >"$log" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-042-regulatory-translation-quality"
[[ -f "$PLAN_DIR/PLAN-042-regulatory-translation-quality.md" ]] \
  && pass "PLAN-042 charter" || fail "missing PLAN-042 charter"
[[ -f "$PLAN_DIR/error-taxonomy.md" ]] && pass "error-taxonomy" || fail "missing taxonomy"
for f in PLAN-042a-taxonomy-fixtures.md PLAN-042b-short-label-direct.md \
         PLAN-042c-word-break.md PLAN-042d-cell-attribution.md \
         PLAN-042e-controlled-entities.md PLAN-042f-warn-delivery.md; do
  [[ -f "$PLAN_DIR/$f" ]] && pass "$f" || fail "missing $f"
done

[[ -f "$ROOT/glossaries/regulatory-form-fields.csv" ]] \
  && pass "regulatory-form-fields.csv" || fail "missing form fields csv"
[[ -f "$ROOT/scripts/apply-pdf2zh-042b-short-label.py" ]] \
  && pass "042b patcher" || fail "missing 042b patcher"
grep -q 'apply-pdf2zh-042b-short-label.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "service patch order" || fail "042b not in pdf2zh.service"
grep -q '042b' "$ROOT/docs/contracts/pdf2zh-patch-order.md" \
  && pass "patch-order doc" || fail "042b missing from patch-order"

run_pass "042 compile" "$STAGE_DIR/compile.log" "$PY" -m compileall -q \
  qyunslation/structure/table_attribution.py \
  qyunslation/structure/regulatory_entities.py \
  qyunslation/structure/page_qc.py \
  qyunslation/structure/table_qc.py \
  qyunslation/structure/table_translate.py \
  qyunslation/structure/table_writeback.py \
  qyunslation/structure/table_execution_observability.py \
  qyunslation/glossary/governance.py \
  scripts/apply-pdf2zh-042b-short-label.py \
  scripts/doc_profile.py

run_pass "042 focused tests" "$STAGE_DIR/tests.log" \
  timeout --signal=INT --kill-after=10s 180s "$PY" -m pytest -q -o addopts= \
    tests/structure/test_plan042_quality.py \
    tests/structure/test_plan041_quality_gates.py \
    tests/structure/test_table_execution_observability.py \
    tests/test_glossary/test_plan039_governance.py

# form layer must appear in merge
if "$PY" - <<'PY'
from qyunslation.glossary.governance import LAYER_PRIORITY, build_merged_dict
assert LAYER_PRIORITY.get("form") == 90
m = build_merged_dict()
assert m.get("双盲") == "Double-blind"
assert "3SBio" in (m.get("三生国健药业（上海）股份有限公司") or "")
print("ok")
PY
then pass "merged form+org lookup"
else fail "merged form+org lookup"
fi

if [[ -n "${QYUNSLATION_PLAN042_SAMPLE:-}" && -f "$QYUNSLATION_PLAN042_SAMPLE" ]]; then
  run_pass "042 real sample gold" "$STAGE_DIR/sample.log" \
    timeout --signal=INT --kill-after=10s 180s env \
    QYUNSLATION_PLAN042_SAMPLE="$QYUNSLATION_PLAN042_SAMPLE" \
    "$PY" -m pytest -q -o addopts= -k "plan042_real_sample"
else
  blocked "QYUNSLATION_PLAN042_SAMPLE missing"
fi

[[ -f "$ROOT/docs/walkthroughs/WT-042-regulatory-translation-quality.md" ]] \
  && pass "WT-042" || fail "missing WT-042"
if grep -q '042b\|短标签\|告警交付' "$ROOT/.cursor/skills/pdf-regulatory-form-fidelity/SKILL.md"; then
  pass "SK-Q003 extended"
else
  fail "SK-Q003 not extended for 042"
fi

if [[ "$BLOCKED" -gt 0 && "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%d fail=0\n' "$BLOCKED"
  exit 2
fi
if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d blocked=%d\n' "$FAILURES" "$BLOCKED"
exit 1

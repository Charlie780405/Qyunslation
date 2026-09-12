#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034 pharma RD MVP — docs + 034d0 implementation gate.
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

PLAN_DIR="$ROOT/docs/plans/PLAN-034-pharma-rd-mvp"
CHARTER="$PLAN_DIR/PLAN-034-pharma-rd-mvp.md"

[[ -f "$CHARTER" ]] && pass "PLAN-034 charter" || fail "missing PLAN-034 charter"

for f in \
  PLAN-034a-gold-benchmark.md \
  PLAN-034b-semantic-policy.md \
  PLAN-034c-saas-persistence.md \
  PLAN-034d0-glossary-ssot-bridge.md \
  PLAN-034d-concept-termbase.md \
  PLAN-034e-translation-memory.md \
  PLAN-034f-model-gateway-qa.md \
  PLAN-034g-human-review-bench.md \
  PLAN-034h-gold-saas-pilot.md \
  README.md
do
  [[ -f "$PLAN_DIR/$f" ]] && pass "$f" || fail "missing $f"
done

if grep -qE '已由 033|033–049 交付' "$CHARTER" \
  && grep -qE '有基座|做增量' "$CHARTER" \
  && grep -qE '真空白|须新建' "$CHARTER"; then
  pass "charter three-state matrix"
else
  fail "charter missing three-state matrix"
fi

if grep -q '034a' "$CHARTER" && grep -q '034d0' "$CHARTER" && grep -q '034h' "$CHARTER"; then
  pass "charter subplan index"
else
  fail "charter missing subplan index"
fi

D0="$PLAN_DIR/PLAN-034d0-glossary-ssot-bridge.md"
E="$PLAN_DIR/PLAN-034e-translation-memory.md"
C="$PLAN_DIR/PLAN-034c-saas-persistence.md"
if grep -q '034c' "$E" && grep -qE '依赖.*034c|034c.*034d' "$E"; then
  pass "034e depends on persistence"
else
  fail "034e must depend on 034c (TM after persistence)"
fi
if grep -qE 'PostgreSQL|租户' "$C"; then
  pass "034c persistence skeleton"
else
  fail "034c missing PG/tenant scope"
fi

if grep -q '370' "$D0" && grep -q '209' "$D0" && grep -q '9429' "$D0"; then
  pass "034d0 measured anchors 370/209/9429"
else
  fail "034d0 missing measured anchors 370 vs 209 / 9429"
fi

FEAS="$ROOT/docs/plans/cursor-import/034可行性评估_a94734a0.plan.md"
if [[ -f "$FEAS" ]] && grep -qE '已复活|PLAN-034-pharma-rd-mvp' "$FEAS"; then
  pass "feasibility marked revived"
else
  fail "feasibility assessment not marked revived"
fi

INDEX="$ROOT/docs/plans/README.md"
if [[ -f "$INDEX" ]] && grep -q 'PLAN-034' "$INDEX"; then
  pass "docs/plans README indexes 034"
else
  fail "docs/plans/README.md missing PLAN-034"
fi

# --- 034d0 implementation ---
if [[ ! -x "$PY" ]]; then
  fail "missing venv python"
else
  if grep -q 'apply_ssot_to_payload' "$ROOT/qyunslation/server/core.py" \
    && grep -q 'apply_ssot_to_payload' "$ROOT/qyunslation/glossary/ssot.py"; then
    pass "034d0 apply_ssot bridge"
  else
    fail "034d0 missing apply_ssot bridge"
  fi

  if grep -q 'filter_glossary_hits' "$ROOT/qyunslation/extensions/glossary_db.py" \
    && grep -q 'build_merged_dict' "$ROOT/qyunslation/extensions/glossary_db.py"; then
    pass "034d0 filter + four-layer preset"
  else
    fail "034d0 missing filter_glossary_hits / build_merged_dict"
  fi

  if grep -q '_normalize_key' "$ROOT/qyunslation/glossary/glossary.py"; then
    pass "034d0 _normalize_key"
  else
    fail "034d0 missing _normalize_key"
  fi

  if grep -q 'ui-increment' "$ROOT/scripts/glossary_merge_runtime.py" \
    && grep -q 'export_ui_increment_csv' "$ROOT/qyunslation/extensions/glossary_db.py"; then
    pass "034d0 ui-increment session export"
  else
    fail "034d0 missing ui-increment path"
  fi

  run_pass "034d0 pytest" "$STAGE_DIR/t.log" \
    "$PY" -m pytest -q --no-cov \
    tests/glossary/test_plan034d0_ssot_bridge.py \
    tests/test_glossary/test_glossary.py \
    tests/test_glossary_db.py

  run_pass "034d0 load_glossary == build_merged_dict" "$STAGE_DIR/c.log" "$PY" - <<'PY'
from qyunslation.extensions import glossary_db
from qyunslation.extensions.glossary_db import load_glossary
from qyunslation.glossary.governance import build_merged_dict
# force empty user overlay for count compare
glossary_db.PRESET_GLOSSARY.clear()
import tempfile
from pathlib import Path
p = Path(tempfile.mkdtemp()) / "empty.json"
p.write_text("{}")
glossary_db.DB_PATH = p
glossary_db.PRESET_GLOSSARY.clear()
g = load_glossary()
m = build_merged_dict()
assert len(g) == len(m), (len(g), len(m))
assert g.get("景行生物") == "GenScend"
print("ok", len(g))
PY
fi

[[ -f "$ROOT/docs/walkthroughs/WT-034d0-glossary-ssot.md" ]] \
  && pass "WT-034d0" || fail "missing WT-034d0"

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%s\n' "$FAILURES"
exit 1

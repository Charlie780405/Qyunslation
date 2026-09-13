#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034d Concept termbase gate.
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

PLAN_D="$ROOT/docs/plans/PLAN-034-pharma-rd-mvp/PLAN-034d-concept-termbase.md"
WT="$ROOT/docs/walkthroughs/WT-034d-concept-termbase.md"

[[ -f "$PLAN_D" ]] && pass "PLAN-034d doc" || fail "missing PLAN-034d"
[[ -f "$WT" ]] && pass "WT-034d" || fail "missing WT-034d"
[[ -f "$ROOT/qyunslation/persist/concept_repo.py" ]] && pass "concept_repo" || fail "concept_repo"
[[ -f "$ROOT/qyunslation/glossary/concept_flatten.py" ]] && pass "concept_flatten" || fail "concept_flatten"
[[ -f "$ROOT/alembic/versions/034d0001_concept_termbase.py" ]] \
  && pass "alembic 034d0001" || fail "alembic 034d0001"
[[ -f "$ROOT/scripts/plan034d-import-csv.py" ]] && pass "import script" || fail "import script"

grep -q 'Concept' "$PLAN_D" && pass "PLAN mentions Concept" || fail "PLAN Concept"
grep -q 'MedDRA' "$PLAN_D" && pass "PLAN MedDRA out-of-scope note" || fail "MedDRA note"

run_pass "imports" "$STAGE_DIR/imp.log" \
  "$PY" -c "
from qyunslation.persist.models import Concept, ConceptTerm, ConceptForbidden
from qyunslation.persist.concept_repo import detect_forbidden
from qyunslation.glossary.concept_flatten import flatten_curated_dict
assert detect_forbidden('a foo b', ['foo'])
print('ok')
"

run_pass "034d pytest" "$STAGE_DIR/t.log" \
  "$PY" -m pytest -q --no-cov tests/persist/test_plan034d_concept.py

run_pass "csv fallback no engine" "$STAGE_DIR/fb.log" \
  "$PY" -c "
from qyunslation.persist.db import reset_engine
from qyunslation.glossary.governance import build_merged_dict
reset_engine()
d = build_merged_dict()
assert len(d) >= 100
assert d.get('景行生物') == 'GenScend'
print('ok', len(d))
"

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s\n' "$FAILURES"
  exit 1
fi
printf 'SUMMARY: PASS fail=0\n'
exit 0

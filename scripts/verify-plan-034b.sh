#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034b Manifest 1.3.0 semantic policy gate.
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

PLAN_B="$ROOT/docs/plans/PLAN-034-pharma-rd-mvp/PLAN-034b-semantic-policy.md"
CONTRACT="$ROOT/docs/contracts/document-structure-manifest-v1.md"
SCHEMA="$ROOT/docs/contracts/document-structure-manifest-v1.schema.json"
WT="$ROOT/docs/walkthroughs/WT-034b-semantic-policy.md"

[[ -f "$PLAN_B" ]] && pass "PLAN-034b doc" || fail "missing PLAN-034b"
[[ -f "$WT" ]] && pass "WT-034b" || fail "missing WT-034b"
[[ -f "$CONTRACT" ]] && pass "manifest contract md" || fail "missing contract md"
[[ -f "$SCHEMA" ]] && pass "manifest schema json" || fail "missing schema"

grep -q '当前版本为 `1.3.0`' "$CONTRACT" \
  && pass "contract version 1.3.0" || fail "contract version not 1.3.0"
grep -q 'TERM_ONLY' "$CONTRACT" && pass "contract TERM_ONLY" || fail "contract TERM_ONLY"
grep -q 'HUMAN_REVIEW' "$SCHEMA" && pass "schema HUMAN_REVIEW" || fail "schema HUMAN_REVIEW"

run_pass "schema version assert" "$STAGE_DIR/ver.log" \
  "$PY" -c "from qyunslation.structure.models import CURRENT_SCHEMA_VERSION; assert CURRENT_SCHEMA_VERSION == '1.3.0'"

run_pass "034b pytest" "$STAGE_DIR/t.log" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_plan034b_manifest_13.py \
    tests/structure/test_manifest_contract.py

run_pass "schema matches model" "$STAGE_DIR/sch.log" \
  "$PY" -c "
import json
from pathlib import Path
from qyunslation.structure.models import DocumentStructureManifest
committed = json.loads(Path('docs/contracts/document-structure-manifest-v1.schema.json').read_text())
assert committed == DocumentStructureManifest.model_json_schema()
"

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s\n' "$FAILURES"
  exit 1
fi
printf 'SUMMARY: PASS fail=0\n'
exit 0

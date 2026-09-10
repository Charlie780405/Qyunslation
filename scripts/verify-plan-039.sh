#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-039 glossary governance gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
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

[[ -x "$PY" ]] || { printf 'SUMMARY: FAIL blocked=1 missing venv python\n'; exit 1; }

# --- docs ---
[[ -f "$ROOT/docs/plans/PLAN-039-glossary-governance/PLAN-039-glossary-governance.md" ]] \
  && pass "PLAN-039 charter" || fail "missing PLAN-039 charter"
for f in \
  PLAN-039a-schema-merge.md \
  PLAN-039b-org-proper-nouns.md \
  PLAN-039c-clinical-lexicon.md \
  PLAN-039d-enrich-promote.md \
  PLAN-039e-runtime-merge.md \
  PLAN-039f-docs-closure.md
do
  [[ -f "$ROOT/docs/plans/PLAN-039-glossary-governance/$f" ]] \
    && pass "$f" || fail "missing $f"
done

# --- curated CSVs ---
[[ -f "$ROOT/glossaries/org-proper-nouns.csv" ]] && pass "org-proper-nouns.csv" || fail "missing org csv"
[[ -f "$ROOT/glossaries/clinical-lifecycle.csv" ]] && pass "clinical-lifecycle.csv" || fail "missing clinical csv"
[[ -f "$ROOT/glossaries/project-overlay.csv" ]] && pass "project-overlay.csv" || fail "missing project csv"

# --- modules / scripts ---
[[ -f "$ROOT/qyunslation/glossary/governance.py" ]] && pass "governance.py" || fail "missing governance.py"
for s in glossary_enrich.py glossary_promote.py glossary_merge_runtime.py; do
  [[ -f "$ROOT/scripts/$s" ]] && pass "$s" || fail "missing $s"
done

# --- unit tests ---
run_pass "039 governance tests" "$STAGE_DIR/t.log" \
  "$PY" -m pytest -q --no-cov tests/test_glossary/test_plan039_governance.py

# --- GenScend / clinical seeds via merge ---
run_pass "039 merge seeds" "$STAGE_DIR/m.log" "$PY" - <<'PY'
from qyunslation.glossary.governance import build_merged_dict
from qyunslation.extensions.glossary_db import load_glossary

m = build_merged_dict()
assert m.get("景行生物") == "GenScend", m.get("景行生物")
assert m.get("江苏景行生物医药有限公司") == "GenScend"
assert m.get("GenScend") == "GenScend"
assert m.get("Jiangsu GenScend Biopharma Co., Ltd.") and "景行" in m["Jiangsu GenScend Biopharma Co., Ltd."]
assert m.get("primary endpoint") == "主要终点"
assert m.get("CRSwNP") == "伴鼻息肉的慢性鼻窦炎"
assert "金斯瑞" not in {m.get("GenScend"), m.get("景行生物")}
g = load_glossary()
assert g.get("primary endpoint") == "主要终点"
assert g.get("atopic dermatitis") == "特应性皮炎"
print("ok", len(m), len(g))
PY

# --- runtime merge dry ---
run_pass "039 merge runtime" "$STAGE_DIR/r.log" \
  "$PY" "$ROOT/scripts/glossary_merge_runtime.py" --print-count

MERGED_RUNTIME="/home/dev/pdf2zh/glossaries/merged.csv"
if [[ -f "$MERGED_RUNTIME" ]]; then
  grep -q '景行生物' "$MERGED_RUNTIME" && pass "runtime merged has 景行" || fail "runtime merged missing 景行"
  grep -q 'primary endpoint' "$MERGED_RUNTIME" && pass "runtime merged has clinical" || fail "runtime merged missing clinical"
else
  fail "runtime merged.csv missing"
fi

# --- sidecar static_csv reads merged ---
run_pass "039 static_csv default" "$STAGE_DIR/s.log" "$PY" - <<'PY'
from qyunslation.glossary.static_csv import load_static_glossary
d = load_static_glossary()
assert d.get("景行生物") == "GenScend", d.get("景行生物")
assert d.get("primary endpoint") == "主要终点"
print("static", len(d))
PY

# --- enrich dry-run smoke ---
run_pass "039 enrich dry-run" "$STAGE_DIR/e.log" \
  "$PY" "$ROOT/scripts/glossary_enrich.py" --dry-run \
  "$ROOT/glossaries/org-proper-nouns.csv"

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1

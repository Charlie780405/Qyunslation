#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-048 table HPD grid fidelity gate.
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
  if "$@" >"$log" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=0 fail=1\n'
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-048-table-hpd-grid"
[[ -f "$PLAN_DIR/PLAN-048-table-hpd-grid.md" ]] \
  && pass "PLAN-048 charter" || fail "missing PLAN-048 charter"
for f in PLAN-048a-hpd-client.md PLAN-048b-align.md PLAN-048c-gates.md \
  PLAN-048d-region-fallback.md PLAN-048e-size-normalize.md PLAN-048f-skill.md; do
  [[ -f "$PLAN_DIR/$f" ]] && pass "$f" || fail "missing $f"
done

# 048a
grep -q 'def hpd_grid\|def _delatex\|def _merge_wrapped_rows' \
  "$ROOT/qyunslation/structure/table_grid_hpd.py" \
  && pass "048a hpd client" || fail "048a hpd client"
grep -q 'QYUNSLATION_HPD_GRID\|hpd-grid' \
  "$ROOT/qyunslation/structure/table_grid_hpd.py" \
  && pass "048a cache/env" || fail "048a cache/env"

# 048b
grep -q 'def structure_table_ex\|def align_hpd_grid\|def gutter_column_centers' \
  "$ROOT/qyunslation/structure/table_structure.py" \
  && pass "048b align/gutter" || fail "048b align/gutter"
grep -q 'PLAN-048b：已废弃\|geometry_center' \
  "$ROOT/qyunslation/structure/table_structure.py" \
  && pass "048b merge retired" || fail "048b merge retired"

# 048c
grep -q 'def assert_grid_source_safe\|def cross_check\|def looks_collapsed\|QC_NOT_A_TABLE' \
  "$ROOT/qyunslation/structure/table_qc.py" \
  && pass "048c gates" || fail "048c gates"
grep -q 'assert_grid_source_safe\|not_a_table' \
  "$ROOT/scripts/pdf_table_translate.py" \
  && pass "048c translate gate" || fail "048c translate gate"

# 048d
grep -q '_expand_region_left\|PLAN-048d' \
  "$ROOT/qyunslation/structure/tables.py" \
  && pass "048d left expand" || fail "048d left expand"
grep -q 'normalize_table_page\|not_a_table' \
  "$ROOT/scripts/pdf_table_translate.py" \
  && pass "048d fallback ladder" || fail "048d fallback ladder"

# 048e
grep -q 'is_header\|header_target\|body_target' \
  "$ROOT/scripts/pdf_table_normalize.py" \
  && pass "048e role bands" || fail "048e role bands"

# 048f
[[ -f "$ROOT/.cursor/skills/table-translation-fidelity/SKILL.md" ]] \
  && pass "048f SKILL.md" || fail "048f SKILL.md"
[[ -f "$ROOT/.cursor/skills/table-translation-fidelity/pitfalls.md" ]] \
  && pass "048f pitfalls" || fail "048f pitfalls"
grep -q 'SK-Q009' "$ROOT/.cursor/skills/skill-registry/registry.md" \
  && pass "048f registry" || fail "048f registry"
grep -q 'SIG-TABLE-SCRAMBLE\|SIG-NOT-A-TABLE\|SIG-HPD-UNREACHABLE' \
  "$ROOT/.cursor/skills/skill-registry/error-signatures.toml" \
  && pass "048f signatures" || fail "048f signatures"

[[ -f "$ROOT/docs/walkthroughs/WT-048-table-hpd-grid.md" ]] \
  && pass "WT-048" || fail "WT-048"

run_pass "048 unit tests" "$STAGE_DIR/pytest.log" \
  "$PY" -m pytest -q \
  tests/structure/test_plan048_hpd_grid.py \
  tests/structure/test_plan046a_gates.py

# HPD health（不可达 → blocked）
if "$PY" - <<'PY'
from qyunslation.structure.table_grid_hpd import hpd_health
raise SystemExit(0 if hpd_health() else 1)
PY
then
  pass "HPD health"
else
  blocked "HPD unreachable (offline OK)"
fi

# optional sample
SAMPLE="${QYUNSLATION_PLAN048_SAMPLE:-}"
if [[ -n "$SAMPLE" && -f "$SAMPLE" ]]; then
  run_pass "048 sample structure" "$STAGE_DIR/sample.log" \
    "$PY" - <<PY
import os, sys
from pathlib import Path
import pymupdf
from qyunslation.structure.tables import table_regions
from qyunslation.structure.table_structure import structure_table_ex

src = Path(os.environ["QYUNSLATION_PLAN048_SAMPLE"])
doc = pymupdf.open(src)
# page indices from prior job: table1 p4, table2 p4, table3 p6
checks = []
for pno, tno, expect in ((4, 1, "hpd"), (4, 2, "not_a_table"), (6, 3, "hpd")):
    page = doc[pno]
    regs = [r for r in table_regions(page) if r.number == tno]
    if not regs:
        print(f"missing region p{pno} t{tno}")
        sys.exit(1)
    r = structure_table_ex(page, regs[0], number=tno)
    print(f"p{pno} t{tno} source={r.grid_source} cols={r.n_cols} rows={r.n_rows} qc={r.qc_codes}")
    if expect == "not_a_table":
        assert r.grid_source == "not_a_table" or "NOT_A_TABLE" in r.qc_codes, r
    else:
        assert r.grid_source in ("hpd", "gutter"), r
        if tno == 1:
            assert r.n_cols == 4, r
        if tno == 3:
            assert r.n_cols >= 6, r
print("sample OK")
PY
else
  blocked "QYUNSLATION_PLAN048_SAMPLE unset"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL blocked=%s fail=%s\n' "$BLOCKED" "$FAILURES"
  exit 1
fi
printf 'SUMMARY: PASS blocked=%s fail=0\n' "$BLOCKED"
exit 0

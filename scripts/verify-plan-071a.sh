#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-071a：基线 / 盘点 / 指纹 / 金标期望契约门禁。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
if [[ -n "${QYUNSLATION_VERIFY_PY:-}" ]]; then
  PY="$QYUNSLATION_VERIFY_PY"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="$(command -v python3 || true)"
fi
FAILURES=0
BLOCKED=0
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

if [[ -z "$PY" || ! -x "$PY" ]]; then
  fail "Python interpreter unavailable; set QYUNSLATION_VERIFY_PY"
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi

REQUIRED=(
  "$ROOT/docs/plans/PLAN-071-translation-quality-pipeline/README.md"
  "$ROOT/docs/plans/PLAN-071-translation-quality-pipeline/PLAN-071a-baseline-inventory.md"
  "$ROOT/docs/contracts/plan071-legacy-capability-inventory.md"
  "$ROOT/docs/contracts/plan071-acceptance-matrix.md"
  "$ROOT/docs/gold/plan071/baseline/MANIFEST.md"
  "$ROOT/docs/gold/plan071/catalog.json"
  "$ROOT/docs/gold/plan071/expectation.schema.json"
  "$ROOT/docs/gold/plan071/expectations/G071-pdf-scan-fda.json"
  "$ROOT/docs/gold/plan071/expectations/G071-pdf-text.json"
  "$ROOT/docs/gold/plan071/expectations/G071-pdf-table-dense.json"
  "$ROOT/docs/gold/plan071/expectations/G071-pdf-figure-dense.json"
  "$ROOT/docs/gold/plan071/expectations/G071-docx.json"
  "$ROOT/docs/gold/plan071/expectations/G071-pptx.json"
  "$ROOT/docs/gold/plan071/expectations/G071-image.json"
  "$ROOT/scripts/plan071_patch_fingerprint.py"
  "$ROOT/docs/walkthroughs/WT-071a-baseline-inventory.md"
)

for f in "${REQUIRED[@]}"; do
  if [[ -f "$f" ]]; then
    pass "exists $(basename "$f")"
  else
    fail "missing $f"
  fi
done

OUT_DIR="$ROOT/artifacts/plan071/baseline"
mkdir -p "$OUT_DIR"
if "$PY" "$ROOT/scripts/plan071_patch_fingerprint.py" -o "$OUT_DIR/patch-fingerprint.json"; then
  pass "patch fingerprint wrote"
else
  fail "patch fingerprint script failed"
fi

if "$PY" -m pytest -q -o addopts= \
  tests/scripts/test_plan071_patch_fingerprint.py \
  tests/gold/test_plan071_expectations_schema.py; then
  pass "pytest 071a"
else
  fail "pytest 071a"
fi

# Real FDA binary is required for later waves; absence blocks sample runs only.
GOLD_ROOT="${QYUNSLATION_PLAN034_GOLD_ROOT:-/home/dev/qyunslation-gold/plan034}"
FDA="$GOLD_ROOT/C-fda-pind.pdf"
if [[ -f "$FDA" ]]; then
  pass "FDA binary present"
else
  blocked "FDA binary absent at $FDA (071a docs OK; sample runs BLOCKED until promoted)"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED fail=0 blocked=%s\n' "$BLOCKED"
  exit 0
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
exit 0

#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-071b：DocumentPipeline / Manifest 2.0 契约门禁。
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
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }

[[ -x "$PY" ]] || { fail "python missing"; exit 1; }

REQUIRED=(
  "$ROOT/qyunslation/pipeline/document_pipeline.py"
  "$ROOT/qyunslation/pipeline/workspace.py"
  "$ROOT/docs/walkthroughs/WT-071b-document-pipeline-manifest.md"
  "$ROOT/tests/pipeline/test_document_pipeline_skeleton.py"
  "$ROOT/tests/api/test_plan071b_launch_formats.py"
)
for f in "${REQUIRED[@]}"; do
  [[ -f "$f" ]] && pass "exists $(basename "$f")" || fail "missing $f"
done

if "$PY" - <<'PY'
from qyunslation.structure.models import CURRENT_SCHEMA_VERSION, SUPPORTED_SCHEMA_MAJORS
assert CURRENT_SCHEMA_VERSION.startswith("2.")
assert 1 in SUPPORTED_SCHEMA_MAJORS and 2 in SUPPORTED_SCHEMA_MAJORS
print("manifest 2.x ok")
PY
then
  pass "manifest version"
else
  fail "manifest version"
fi

if QYUNSLATION_PIPELINE=v2 "$PY" -m pytest -q -o addopts= \
  tests/pipeline/ \
  tests/structure/test_manifest_v2_schema.py \
  tests/api/test_plan071b_launch_formats.py \
  tests/workbench/test_plan066e_runner.py \
  tests/persist/test_plan066e_pdf_runner.py \
  tests/structure/test_manifest_contract.py; then
  pass "pytest 071b"
else
  fail "pytest 071b"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s\n' "$FAILURES"
  exit 1
fi
printf 'SUMMARY: PASS fail=0\n'
exit 0

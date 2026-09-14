#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-059：医药资料翻译保真与工作台 UI 三态门禁。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  COMMON_GIT_DIR="$(git -C "$ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
  if [[ -n "$COMMON_GIT_DIR" ]]; then
    COMMON_ROOT="$(cd "$(dirname "$COMMON_GIT_DIR")" 2>/dev/null && pwd || true)"
    [[ -x "${COMMON_ROOT:-}/.venv/bin/python" ]] && PY="$COMMON_ROOT/.venv/bin/python"
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

PLAN_DIR="$ROOT/docs/plans/PLAN-059-translation-fidelity"
WT="$ROOT/docs/walkthroughs/WT-059-translation-fidelity.md"
for required in \
  "$PLAN_DIR/README.md" \
  "$PLAN_DIR/PLAN-059a-baseline-and-contract.md" \
  "$PLAN_DIR/PLAN-059b-appbar-layout.md" \
  "$PLAN_DIR/PLAN-059c-structure-truth.md" \
  "$PLAN_DIR/PLAN-059d-reference-and-style.md" \
  "$PLAN_DIR/PLAN-059e-image-rendering.md" \
  "$PLAN_DIR/PLAN-059f-table-execution.md" \
  "$PLAN_DIR/PLAN-059g-column-layout.md" \
  "$PLAN_DIR/PLAN-059h-model-and-termbase.md" \
  "$PLAN_DIR/PLAN-059i-gates-and-delivery.md" \
  "$WT" \
  "$ROOT/qyunslation/structure/references.py" \
  "$ROOT/qyunslation/structure/table_translate.py" \
  "$ROOT/qyunslation/extensions/doc_image_policy.py" \
  "$ROOT/scripts/apply-pdf2zh-050-workbench.py"; do
  if [[ -f "$required" ]]; then
    pass "static $(basename "$required")"
  else
    fail "missing $required"
  fi
done

if "$PY" -m compileall -q \
  qyunslation/agents qyunslation/extensions qyunslation/structure \
  qyunslation/workflow qyunslation/translator/ai_translator; then
  pass "PLAN-059 modules compile"
else
  fail "PLAN-059 modules compile"
fi

if "$PY" -m pytest -q --no-cov \
  tests/structure/test_plan059_fidelity.py \
  tests/structure/test_scan_pdf.py \
  tests/structure/test_scan_docx.py \
  tests/structure/test_scan_pptx.py \
  tests/structure/test_scan_image.py \
  tests/structure/test_plan033j_table_translate.py \
  tests/structure/test_plan044_quality.py \
  tests/ui/test_appbar_upload_actions.py \
  tests/ui/test_plan050_state_manifest.py \
  tests/test_plan033c_imgtr_post.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "PLAN-059 focused pytest"
else
  fail "PLAN-059 focused pytest"
  tail -n 80 "$STAGE_DIR/pytest.log" || true
fi

SAMPLE="${QYUNSLATION_PLAN059_SAMPLE:-}"
if [[ -z "$SAMPLE" && -n "${QYUNSLATION_SAMPLE_ROOT:-}" ]]; then
  for candidate in \
    "$QYUNSLATION_SAMPLE_ROOT/ljae439.pdf" \
    "$QYUNSLATION_SAMPLE_ROOT/1-s2.0-S2666636725013958-main.pdf"; do
    if [[ -f "$candidate" ]]; then SAMPLE="$candidate"; break; fi
  done
fi
if [[ -z "$SAMPLE" ]]; then
  SAMPLE="$ROOT/tests/fixtures/structure/reference/ljae439.pdf"
fi
if [[ -f "$SAMPLE" ]]; then
  pass "journal structure sample present ($(basename "$SAMPLE"))"
else
  blocked "PLAN-059 sample missing; set QYUNSLATION_PLAN059_SAMPLE or QYUNSLATION_SAMPLE_ROOT"
fi

# A LIVE result is deliberately separate from configuration provenance.  The
# probe exits 2 for an unavailable/mismatched remote service, which is a
# BLOCKED gate and never a fabricated PASS.
if [[ "${QYUNSLATION_PLAN059_LIVE:-}" == "1" || "${QYUNSLATION_PLAN059_LIVE:-}" == "true" ]]; then
  set +e
  "$PY" - <<'PY' >"$STAGE_DIR/live.log" 2>&1
import json
import sys

from qyunslation.embed.client import embed_health
from qyunslation.gateway.provider import ping_provider
from qyunslation.structure.model_trace import (
    EXPECTED_EMBEDDING_MODEL,
    EXPECTED_TRANSLATION_MODEL,
)

translation = ping_provider()
embedding = embed_health()
print(json.dumps({"translation": translation, "embedding": embedding}, ensure_ascii=False, sort_keys=True))
if translation.get("live") is not True or translation.get("model_id") != EXPECTED_TRANSLATION_MODEL:
    print("target translation model is not confirmed LIVE", file=sys.stderr)
    raise SystemExit(2)
if embedding.get("live") is not True or embedding.get("model") != EXPECTED_EMBEDDING_MODEL:
    print("target embedding model is not confirmed LIVE", file=sys.stderr)
    raise SystemExit(2)
PY
  code=$?
  set -e
  if [[ "$code" -eq 0 ]]; then
    pass "Taizhou Qwen/bge-m3 LIVE model probe"
    cat "$STAGE_DIR/live.log"
  elif [[ "$code" -eq 2 ]]; then
    blocked "Taizhou Qwen/bge-m3 LIVE model probe"
    cat "$STAGE_DIR/live.log"
  else
    fail "Taizhou model probe execution"
    cat "$STAGE_DIR/live.log"
  fi
else
  pass "LIVE model probe skipped (set QYUNSLATION_PLAN059_LIVE=1)"
fi

if [[ "${QYUNSLATION_PLAN059_FULL:-}" == "1" || "${QYUNSLATION_PLAN059_FULL:-}" == "true" ]]; then
  for gate in 028 029 030e 034 041 045 050 058; do
    log="$STAGE_DIR/dependency-$gate.log"
    if [[ ! -x "$ROOT/scripts/verify-plan-$gate.sh" ]]; then
      fail "missing dependency gate PLAN-$gate"
      continue
    fi
    if bash "$ROOT/scripts/verify-plan-$gate.sh" >"$log" 2>&1; then
      pass "dependency gate PLAN-$gate"
    else
      code=$?
      if [[ "$code" -eq 2 ]] || grep -q '^SUMMARY: BLOCKED' "$log"; then
        blocked "dependency gate PLAN-$gate"
      else
        fail "dependency gate PLAN-$gate"
      fi
      tail -n 35 "$log" || true
    fi
  done
else
  pass "dependency gates skipped (set QYUNSLATION_PLAN059_FULL=1)"
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

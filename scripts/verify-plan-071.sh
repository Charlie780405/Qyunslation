#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-071：翻译质量管线总验收（缺浏览器证据则 BLOCKED）。
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

[[ -x "$PY" ]] || { fail "python missing"; exit 1; }

REQUIRED=(
  "$ROOT/qyunslation/pipeline/document_pipeline.py"
  "$ROOT/qyunslation/pipeline/atomic_spans.py"
  "$ROOT/qyunslation/pipeline/event_store.py"
  "$ROOT/qyunslation/pipeline/qa/engine.py"
  "$ROOT/qyunslation/pipeline/model_profiles.py"
  "$ROOT/qyunslation/glossary/redaction.py"
  "$ROOT/frontend/src/next/components/StageTimeline.vue"
  "$ROOT/frontend/src/next/pages/RunDetailPage.vue"
  "$ROOT/docs/walkthroughs/WT-071-translation-quality-pipeline.md"
  "$ROOT/alembic/versions/071d0001_stage_events_quality_models.py"
  "$ROOT/alembic/versions/071i0001_legacy_unverified_backfill.py"
)
for f in "${REQUIRED[@]}"; do
  [[ -f "$f" ]] && pass "exists $(basename "$f")" || fail "missing $f"
done

if env -u QYUNSLATION_PIPELINE "$PY" -m pytest -q -o addopts= \
  tests/pipeline/test_atomic_spans.py \
  tests/pipeline/test_progress_units.py \
  tests/pipeline/test_events_reconcile.py \
  tests/pipeline/test_model_profile_probe.py \
  tests/pipeline/qa/test_categories_basic.py \
  tests/glossary/test_plan071h_redaction.py \
  tests/glossary/test_plan071h_suggestion_schema.py \
  tests/glossary/test_plan071h_cache_key.py \
  tests/ui/test_plan071d_no_hardcoded_stages.py \
  tests/ui/test_plan071f_run_detail_route.py \
  tests/ui/test_plan071g_settings_source.py \
  tests/persist/test_plan071i_legacy_backfill.py
then
  pass "pytest 071 unit/ui contracts"
else
  fail "pytest 071 unit/ui contracts"
fi

if QYUNSLATION_PIPELINE=v2 "$PY" -m pytest -q -o addopts= \
  tests/api/test_plan071d_events_api.py \
  tests/api/test_plan071e_review_gate.py \
  tests/api/test_plan071e_download_bypass.py \
  tests/api/test_plan071g_model_classification_gate.py \
  tests/api/test_plan071i_retry_v2.py
then
  pass "pytest 071 api gates"
else
  fail "pytest 071 api gates"
fi

if [[ -x "$ROOT/scripts/verify-plan-071a.sh" ]]; then
  if bash "$ROOT/scripts/verify-plan-071a.sh"; then pass "verify-071a"; else fail "verify-071a"; fi
fi
if [[ -x "$ROOT/scripts/verify-plan-071b.sh" ]]; then
  if bash "$ROOT/scripts/verify-plan-071b.sh"; then pass "verify-071b"; else fail "verify-071b"; fi
fi

EVIDENCE_DIR="$ROOT/artifacts/plan071"
BROWSER_MARKERS=(
  "login"
  "upload"
  "stage-progress"
  "preview"
  "settings"
  "review"
  "download"
)
if [[ -d "$EVIDENCE_DIR" ]]; then
  for marker in "${BROWSER_MARKERS[@]}"; do
    if compgen -G "$EVIDENCE_DIR/*${marker}*" > /dev/null; then
      pass "browser evidence $marker"
    else
      blocked "missing browser evidence for $marker"
    fi
  done
else
  blocked "artifacts/plan071 missing — Chrome DevTools evidence required for release"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED fail=0 blocked=%s\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
exit 0

#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-076i: documented rollback drill for AD pilot mode.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECK_ONLY=0
for arg in "$@"; do
  if [[ "$arg" == "--check-only" ]]; then
    CHECK_ONLY=1
  fi
done

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; exit 1; }

required=(
  "docs/plans/PLAN-076-ad-bilingual-prompt-quality-system/PLAN-076i-gap-remediation.md"
  "qyunslation/pipeline/ad_runtime.py"
  "scripts/verify-plan-076.sh"
)
for path in "${required[@]}"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  pass "rollback drill checklist available"
  cat <<'EOF'
Rollback steps (manual on production host):
1. export QYUNSLATION_AD_PROMPT_MODE=off
2. bash scripts/deploy-translate-stack.sh
3. curl -sf http://127.0.0.1:8010/api/v1/health
4. Confirm /api/v1/me returns ad_enabled=false for non-allowlisted tenants
5. Archive var/ad-audit/ad-events-*.jsonl for the mode change window
EOF
  exit 0
fi

echo "Use --check-only to print rollback steps without touching services."
exit 0

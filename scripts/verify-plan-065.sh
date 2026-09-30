#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-065：专业词汇检查器关闭与入库复用说明。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  COMMON_GIT_DIR="$(git -C "$ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
  COMMON_ROOT="$(cd "$(dirname "${COMMON_GIT_DIR:-/nonexistent}")" 2>/dev/null && pwd || true)"
  [[ -x "${COMMON_ROOT:-}/.venv/bin/python" ]] && PY="$COMMON_ROOT/.venv/bin/python"
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

PLAN_DIR="$ROOT/docs/plans/PLAN-065-inspector-close-reuse"
WT="$ROOT/docs/walkthroughs/WT-065-inspector-close-reuse.md"
PATCH060="$ROOT/scripts/apply-pdf2zh-060-termbase-workbench.py"
PATCH050="$ROOT/scripts/apply-pdf2zh-050-workbench.py"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"

for required in \
  "$PLAN_DIR/README.md" \
  "$PLAN_DIR/PLAN-065-inspector-close-reuse.md" \
  "$WT" \
  "$PATCH060" \
  "$PATCH050"; do
  [[ -f "$required" ]] && pass "static $(basename "$required")" || fail "missing $required"
done

grep -q 'PLAN-065-inspector-close-reuse' "$ROOT/docs/plans/README.md" \
  && pass "plans index PLAN-065" || fail "plans index missing PLAN-065"
grep -q '_qy060_close_inspector' "$PATCH060" \
  && pass "close hides Gradio inspector" || fail "close handler missing"
grep -q '关闭 / 返回列表' "$PATCH060" \
  && fail "old close label still present" || pass "old close label removed"
grep -q '#qy050-inspector\[data-open="false"\]' "$PATCH050" \
  && pass "JS drawer hide CSS" || fail "JS drawer hide CSS missing"
grep -q 'qy060-insp-close' "$PATCH050" \
  && pass "Escape clicks Gradio close" || fail "Escape does not click close"
if grep -q 'QYUNSLATION_TERM_BRIDGE_SECRET' "$PATCH060"; then
  fail "GUI patch must not expose bridge secret"
else
  pass "GUI patch contains no bridge secret"
fi

if "$PY" -m compileall -q scripts/apply-pdf2zh-060-termbase-workbench.py scripts/apply-pdf2zh-050-workbench.py; then
  pass "PLAN-065 patches compile"
else
  fail "PLAN-065 patches compile"
fi

if "$PY" -m pytest -q --no-cov \
  tests/ui/test_plan065_inspector_close.py \
  tests/ui/test_plan060_workbench_patch.py \
  tests/ui/test_plan064_workbench_patch.py \
  tests/ui/test_plan050_workbench_patch.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "PLAN-065 focused pytest"
else
  fail "PLAN-065 focused pytest"
  tail -n 80 "$STAGE_DIR/pytest.log" || true
fi

if [[ -f "$GUI" ]]; then
  if grep -q '_qy060_close_inspector' "$GUI" \
    && grep -q '#qy050-inspector\[data-open="false"\]' "$GUI"; then
    pass "live gui.py has close + drawer hide"
  else
    blocked "live gui.py not yet patched; run apply-pdf2zh-050/060 then deploy"
  fi
else
  blocked "pdf2zh-next GUI not installed"
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

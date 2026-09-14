#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-050：工作台 UI 三态门禁
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

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL fail=1 blocked=0\n'
  exit 1
fi

PLAN="$ROOT/docs/plans/PLAN-050-qyunslation-ui-ux"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"

[[ -f "$PLAN/PLAN-050-qyunslation-ui-ux.md" ]] && pass "PLAN-050 charter" || fail "PLAN-050 charter"
for f in PLAN-050a-runtime-baseline.md PLAN-050b-workbench-shell.md \
  PLAN-050c-upload-preflight-task.md PLAN-050d-bilingual-canvas.md \
  PLAN-050e-review-inspector-qa.md PLAN-050f-responsive-accessibility.md \
  PLAN-050g-verify-delivery.md README.md; do
  [[ -f "$PLAN/$f" ]] && pass "$f" || fail "$f"
done
for w in WT-050a-runtime-baseline.md WT-050b-workbench-shell.md \
  WT-050c-upload-preflight-task.md WT-050d-bilingual-canvas.md \
  WT-050e-review-inspector-qa.md WT-050f-responsive-accessibility.md \
  WT-050g-ui-ux-delivery.md; do
  [[ -f "$ROOT/docs/walkthroughs/$w" ]] && pass "$w" || fail "$w"
done
[[ -f "$ROOT/docs/contracts/ui-runtime-050.md" ]] && pass "ui-runtime-050" || fail "ui-runtime-050"
[[ -f "$ROOT/scripts/apply-pdf2zh-050-workbench.py" ]] && pass "050 patch" || fail "050 patch"
[[ -f "$ROOT/qyunslation/ui/manifest_view.py" ]] && pass "manifest_view" || fail "manifest_view"
grep -q 'apply-pdf2zh-050-workbench.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "service 050" || fail "service 050"
grep -q 'apply-pdf2zh-050-workbench.py' "$ROOT/docs/contracts/pdf2zh-patch-order.md" \
  && pass "patch-order 050" || fail "patch-order 050"

if "$PY" -m pytest -q --no-cov \
  tests/ui/test_runtime_surface_050.py \
  tests/ui/test_plan050_state_manifest.py \
  tests/ui/test_plan050_workbench_patch.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "plan050 pytest"
else
  fail "plan050 pytest"
  tail -n 40 "$STAGE_DIR/pytest.log" || true
fi

if [[ -f "$GUI" ]] && grep -Eq 'qy_mode = gr\.(Radio|Dropdown)' "$GUI" && grep -q 'qy_mode.change' "$GUI" \
  && grep -q '_qy_050_workbench_css' "$GUI" && ! grep -q '_qy_050_workbench_js' "$GUI"; then
  pass "gui.py has 050 interactive bar (no js= hijack)"
else
  fail "gui.py 050 chrome missing or js= still hijacked"
fi

if ss -ltn 2>/dev/null | grep -q ':7860'; then
  curl -sS -o "$STAGE_DIR/login.html" http://127.0.0.1:7860/ || true
  if grep -q 'Qyunslation' "$STAGE_DIR/login.html"; then
    pass "live login page"
  else
    fail "live login page"
  fi
  if [[ -f /home/dev/pdf2zh/office.env ]]; then
    USER=$(grep '^QYUNSLATION_GUI_USER=' /home/dev/pdf2zh/office.env | cut -d= -f2-)
    PASS=$(grep '^QYUNSLATION_GUI_PASS=' /home/dev/pdf2zh/office.env | cut -d= -f2-)
    if [[ -n "${USER:-}" && -n "${PASS:-}" ]]; then
      curl -sS -c "$STAGE_DIR/ck" -o /dev/null \
        -X POST 'http://127.0.0.1:7860/login' \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode "username=$USER" \
        --data-urlencode "password=$PASS" || true
      curl -sS -b "$STAGE_DIR/ck" -o "$STAGE_DIR/app.html" http://127.0.0.1:7860/ || true
      if grep -q 'qy-col-left' "$STAGE_DIR/app.html" && grep -q 'qy-050-appbar' "$STAGE_DIR/app.html"; then
        pass "live workbench chrome"
      else
        fail "live workbench chrome (need 050 patch + restart)"
      fi
    else
      blocked "GUI user/pass unset"
    fi
  else
    blocked "office.env missing"
  fi
else
  blocked "7860 down"
fi

if [[ "${QYUNSLATION_PLAN050_LIVE:-}" == "1" || "${QYUNSLATION_PLAN050_LIVE:-}" == "true" ]]; then
  SAMPLE="$ROOT/tests/fixtures/structure/reference/ljae439.pdf"
  if [[ -f "$SAMPLE" ]]; then
    pass "LIVE sample present (ljae439.pdf)"
  else
    blocked "LIVE sample matrix: ljae439.pdf not on disk"
  fi
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

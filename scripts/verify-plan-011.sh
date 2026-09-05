#!/usr/bin/env bash
# verify-plan-011.sh — 正式书信生产重绘
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-python3}"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
pass=0
fail=0
check() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS: $desc"
    pass=$((pass + 1))
  else
    echo "FAIL: $desc"
    fail=$((fail + 1))
  fi
}
echo "== PLAN-011 verify =="
check "letter_pipeline.py" test -f "$ROOT/scripts/letter_pipeline.py"
check "unit letter_pipeline" "$PY" -m unittest scripts.test_letter_pipeline
check "unit kv_reinsert" "$PY" -m unittest scripts.test_kv_reinsert
check "apply 含 letter marker" grep -q '_qy_letter_reflow' "$ROOT/scripts/apply-pdf2zh-docprofile.py"
check "letter 必写 debug" grep -q 'profile or "").strip() == "letter"' "$ROOT/scripts/hpd_ocr.py"
check "service 含 docprofile" grep -q 'apply-pdf2zh-docprofile.py' "$ROOT/scripts/pdf2zh.service"
check "gui 可解析" "$PY" -c "import ast; ast.parse(open(r'$GUI').read())"
check "gui 已打 letter hook" grep -q '_qy_letter_reflow' "$GUI"
echo "verify-plan-011: $pass/$((pass + fail))"
[[ "$fail" -eq 0 ]]

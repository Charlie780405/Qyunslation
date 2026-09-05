#!/usr/bin/env bash
# verify-plan-015.sh — 翻译进度双绑定 + 一屏布局 + doc_profile 自定义值
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUI="${PDF2ZH_GUI:-/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py}"
PY="${PYTHON:-python3}"

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

check "gui 含 show_progress_on 双预览" grep -q 'show_progress_on=\[preview, preview_html\]' "$GUI"
check "gui 含 qy-main-inner-row" grep -q 'qy-main-inner-row' "$GUI"
check "gui 含 qy-col-left" grep -q 'qy-col-left' "$GUI"
check "gui 含 qy-col-right" grep -q 'qy-col-right' "$GUI"
check "gui 含 --qy-shell-top" grep -q -- '--qy-shell-top' "$GUI"
check "gui 空壳 CSS 含 progress 例外" grep -q 'progress-text' "$GUI"
check "gui 隐藏 Gradio footer" grep -q 'footer {' "$GUI"
check "gui Group 隐藏不覆盖" grep -q 'gr-group:not(.hide)' "$GUI"
check "gui settings 排除 overflow hidden" grep -q ':not(.settings-container)' "$GUI"
check "gui settings-container 可内滚" grep -q 'settings-container' "$GUI"
check "doc_profile allow_custom_value" bash -c "
  awk '/doc_profile_dropdown = gr.Dropdown/,/\)/' \"$GUI\" | grep -q 'allow_custom_value=True'
"
check "gui 语法" /home/dev/.local/share/uv/tools/pdf2zh-next/bin/python -m py_compile "$GUI"
check "office-preview 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-office-preview.py' 2>&1 | grep -qE 'already patched|patched:'"
check "docprofile 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-docprofile.py' 2>&1 | grep -qE 'already patched|patched:'"
check "pdf2zh 服务 active" systemctl --user is-active pdf2zh.service

echo "verify-plan-015: $pass/$((pass + fail))"
test "$fail" -eq 0

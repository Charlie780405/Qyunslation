#!/usr/bin/env bash
# verify-plan-017.sh — 双预览 2:4:4 + 进度槽位
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUI="${PDF2ZH_GUI:-/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py}"
PY="${PYTHON:-python3}"
UNIT="${HOME}/.config/systemd/user/pdf2zh.service"

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

check "补丁脚本存在" test -f "$ROOT/scripts/apply-pdf2zh-dual-preview.py"
check "gui 含 _qy_dual_preview" grep -q '# _qy_dual_preview$' "$GUI"
check "左栏 scale=2" grep -q 'scale=2, elem_classes=\["qy-col-left"\]' "$GUI"
check "中栏 scale=4" grep -q 'scale=4, elem_classes=\["qy-col-mid"\]' "$GUI"
check "右栏 scale=4" grep -q 'scale=4, elem_classes=\["qy-col-right"\]' "$GUI"
check "preview_src 唯一定义" bash -c 'c=$(grep -cE "^[[:space:]]*preview_src = PDF" "'"$GUI"'"); test "$c" = 1'
check "qy_progress_slot 唯一定义" bash -c 'c=$(grep -cE "^[[:space:]]*qy_progress_slot = gr\\.HTML" "'"$GUI"'"); test "$c" = 1'
check "show_progress_on 绑进度槽" grep -q 'show_progress_on=\[qy_progress_slot\]' "$GUI"
check "_qy_dual_payload 存在" grep -q 'def _qy_dual_payload(' "$GUI"
check "File(s) 标题已移除" bash -c '! grep -qE "Markdown\\(_\\(\"## File\\(s\\)\"\\)" "'"$GUI"'"'
check "原文/译文标题" bash -c 'grep -q "## 原文" "'"$GUI"'" && grep -q "## 译文" "'"$GUI"'"'
check "行内页脚" grep -q '_qy_dual_preview_footer' "$GUI"
check "dual CSS" grep -q '_qy_dual_preview_css' "$GUI"
check "gui 语法" /home/dev/.local/share/uv/tools/pdf2zh-next/bin/python -m py_compile "$GUI"
check "dual-preview 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-dual-preview.py' 2>&1 | grep -qE 'already patched|patched:'"
check "service 含 dual-preview ExecStartPre" grep -q 'apply-pdf2zh-dual-preview.py' "$ROOT/scripts/pdf2zh.service"
check "user unit 含 dual-preview" grep -q 'apply-pdf2zh-dual-preview.py' "$UNIT"
check "pdf2zh 服务 active" systemctl --user is-active pdf2zh.service

echo "verify-plan-017: $pass/$((pass + fail))"
test "$fail" -eq 0

#!/usr/bin/env bash
# verify-plan-017b.sh — 进度左栏 + 双框等高 + 页脚细条
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

check "补丁脚本存在" test -f "$ROOT/scripts/apply-pdf2zh-layout-polish.py"
check "service 含 layout-polish ExecStartPre" grep -q 'apply-pdf2zh-layout-polish.py' "$ROOT/scripts/pdf2zh.service"
check "user unit 含 layout-polish" grep -q 'apply-pdf2zh-layout-polish.py' "$UNIT"
check "gui 含 polish marker" grep -q '_qy_layout_polish' "$GUI"
check "polish CSS" grep -q '_qy_layout_polish_css' "$GUI"
check "selector 唯一定义" bash -c 'c=$(grep -cE "^[[:space:]]*result_file_selector = gr\\.Dropdown" "'"$GUI"'"); test "$c" = 1'
check "progress 唯一定义" bash -c 'c=$(grep -cE "^[[:space:]]*qy_progress_slot = gr\\.HTML" "'"$GUI"'"); test "$c" = 1'
check "show_progress_on 仍绑槽位" grep -q 'show_progress_on=\[qy_progress_slot\]' "$GUI"
check "页码联动 JS" bash -c 'grep -qE "_qy_page_sync_blocks|_qy_page_sync" "'"$GUI"'"'
check "gui 语法" /home/dev/.local/share/uv/tools/pdf2zh-next/bin/python -m py_compile "$GUI"
check "layout-polish 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-layout-polish.py' 2>&1 | grep -qE 'already patched|patched:'"
check "pdf2zh 服务 active" systemctl --user is-active pdf2zh.service

# Structural placement checks in one Python pass
STRUCT_OK=0
GUI_PATH="$GUI" "$PY" - <<'PY' && STRUCT_OK=1
from pathlib import Path
import os
t = Path(os.environ["GUI_PATH"]).read_text(encoding="utf-8")
left = t.find('elem_classes=["qy-col-left"]')
mid = t.find('elem_classes=["qy-col-mid"]')
right = t.find('elem_classes=["qy-col-right"]')
footer = t.find("_qy_dual_preview_footer", right)
assert left >= 0 and mid > left and right > mid
body = t[left:mid]
assert body.count("result_file_selector = gr.Dropdown") == 1
assert body.count("qy_progress_slot = gr.HTML") == 1
sel = body.find("result_file_selector = gr.Dropdown")
prog = body.find("qy_progress_slot = gr.HTML")
title = body.find('gr.Markdown(_("## Translation Options")')
assert 0 <= sel < prog < title
assert "result_file_selector" not in t[mid:right]
assert "qy_progress_slot = gr.HTML" not in t[right:footer]
dual = t.find("/* _qy_dual_preview_css */")
polish = t.find("/* _qy_layout_polish_css */")
assert dual >= 0 and polish > dual
print("ok")
PY

if [[ "$STRUCT_OK" -eq 1 ]]; then
  echo "PASS: 组件归位与 CSS 顺序"
  pass=$((pass + 1))
else
  echo "FAIL: 组件归位与 CSS 顺序"
  fail=$((fail + 1))
fi

echo "verify-plan-017b: $pass/$((pass + fail))"
test "$fail" -eq 0

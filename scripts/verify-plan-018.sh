#!/usr/bin/env bash
# verify-plan-018.sh — 高级选项下移 + flex-wrap 修复
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

check "补丁脚本存在" test -f "$ROOT/scripts/apply-pdf2zh-adv-options.py"
check "service 含 adv-options ExecStartPre" grep -q 'apply-pdf2zh-adv-options.py' "$ROOT/scripts/pdf2zh.service"
check "user unit 含 adv-options" grep -q 'apply-pdf2zh-adv-options.py' "$UNIT"
check "gui 含 adv css" grep -q '_qy_adv_options_css' "$GUI"
check "flex-wrap nowrap" grep -q 'flex-wrap: nowrap' "$GUI"
check "gui 语法" /home/dev/.local/share/uv/tools/pdf2zh-next/bin/python -m py_compile "$GUI"
check "adv-options 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-adv-options.py' 2>&1 | grep -qE 'already patched|patched:'"
check "pdf2zh 服务 active" systemctl --user is-active pdf2zh.service

STRUCT_OK=0
GUI_PATH="$GUI" "$PY" - <<'PY' && STRUCT_OK=1
from pathlib import Path
import os, re
t = Path(os.environ["GUI_PATH"]).read_text(encoding="utf-8")
left = t.find('elem_classes=["qy-col-left"]')
mid = t.find('elem_classes=["qy-col-mid"]')
assert left >= 0 and mid > left
body = t[left:mid]
action_i = body.find('with gr.Row(elem_classes=["action-row"])')
acc_i = body.find('elem_classes=["qy-adv-acc"]')
assert action_i >= 0 and acc_i > action_i
assert body.count('elem_classes=["qy-adv-acc"]') == 1
sb = body.find("save_btn = gr.Button")
assert sb >= 0 and "visible=False" in body[sb : sb + 400]
cs = t.find('custom_css = """')
assert cs >= 0
c0 = cs + len('custom_css = """')
m = re.search(r'\n[ \t]*"""', t[c0:])
assert m
css_body = t[c0 : c0 + m.start()]
assert css_body.count("/* _qy_adv_options_css */") == 1
assert "flex-wrap: nowrap" in css_body
assert t.count("/* _qy_adv_options_css */") == 1
polish = css_body.find("/* _qy_layout_polish_css */")
adv = css_body.find("/* _qy_adv_options_css */")
assert polish >= 0 and adv > polish
print("ok")
PY

if [[ "$STRUCT_OK" -eq 1 ]]; then
  echo "PASS: 手风琴归位与 CSS 顺序"
  pass=$((pass + 1))
else
  echo "FAIL: 手风琴归位与 CSS 顺序"
  fail=$((fail + 1))
fi

echo "verify-plan-018: $pass/$((pass + fail))"
test "$fail" -eq 0

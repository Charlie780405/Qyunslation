#!/usr/bin/env bash
# verify-plan-016.sh — 设置项内联左栏 + 取消配置入口
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

check "补丁脚本存在" test -f "$ROOT/scripts/apply-pdf2zh-settings-inline.py"
check "gui 含 _qy_settings_inline" grep -q '# _qy_settings_inline$' "$GUI"
check "gui 含高级选项 Accordion" grep -q 'elem_classes=\["qy-adv-acc"\]' "$GUI"
check "gui 含 doc_profile.change" grep -q '_qy_doc_profile_change' "$GUI"
check "gui 含 inline CSS" grep -q '_qy_settings_inline_css' "$GUI"
check "gui CSS 隐藏 sidebar-nav" bash -c "grep -A8 '_qy_settings_inline_css' \"$GUI\" | grep -q 'sidebar-nav'"
check "gui CSS 隐藏 settings-container" bash -c "grep -A20 '_qy_settings_inline_css' \"$GUI\" | grep -q 'settings-container'"
check "sidebar 按钮 visible=False" grep -q 'elem_classes=\["sidebar-btn"\], visible=False)' "$GUI"
check "doc_profile 在 action-row 前" "$PY" -c "
from pathlib import Path
t = Path('$GUI').read_text()
s = t.find('# _qy_settings_inline\n')
a = t.find('with gr.Row(elem_classes=[\"action-row\"])')
raise SystemExit(0 if (s >= 0 and a > s) else 1)
"
check "各搬迁控件唯一定义" "$PY" -c "
import re
from pathlib import Path
t = Path('$GUI').read_text()
for n in ['doc_profile_dropdown','page_range','page_input','only_include_translated_page','glossary_file','ignore_cache','watermark_output_mode','save_btn']:
    c = len(re.findall(rf'^\s*{n}\s*=\s*gr\.', t, re.M))
    assert c == 1, (n, c)
"
check "lang_selector.render 仅 1 处调用" "$PY" -c "
import re
from pathlib import Path
t = Path('$GUI').read_text()
c = len(re.findall(r'(?m)^\s+lang_selector\.render\(\)\s*$', t))
raise SystemExit(0 if c == 1 else 1)
"
check "settings 页无 page_range 定义" "$PY" -c "
from pathlib import Path
t = Path('$GUI').read_text()
# 设置页起点到文末不应再出现 page_range = gr.Radio（已搬到左栏）
idx = t.find('elem_classes=[\"settings-container\"]')
chunk = t[idx:] if idx >= 0 else ''
raise SystemExit(0 if 'page_range = gr.Radio' not in chunk else 1)
"
check "fixed_param_names 未改长度" "$PY" -c "
import re
from pathlib import Path
t = Path('$GUI').read_text()
m = re.search(r'fixed_param_names = \\[(.*?)\\]', t, re.S)
names = re.findall(r'\"(\w+)\"', m.group(1))
assert len(names) == 49, len(names)
assert names[0] == 'service' and names[3] == 'page_range'
"
check "gui 语法" /home/dev/.local/share/uv/tools/pdf2zh-next/bin/python -m py_compile "$GUI"
check "settings-inline 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-settings-inline.py' 2>&1 | grep -qE 'already patched|patched:'"
check "service 含 settings-inline ExecStartPre" grep -q 'apply-pdf2zh-settings-inline.py' "$ROOT/scripts/pdf2zh.service"
check "user unit 含 settings-inline" grep -q 'apply-pdf2zh-settings-inline.py' "$UNIT"
check "pdf2zh 服务 active" systemctl --user is-active pdf2zh.service

echo "verify-plan-016: $pass/$((pass + fail))"
test "$fail" -eq 0

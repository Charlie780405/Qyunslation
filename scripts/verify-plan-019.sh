#!/usr/bin/env bash
# verify-plan-019.sh — 吸底 + 图片导出 + 中英互译透传
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUI="${PDF2ZH_GUI:-/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py}"
PY="${PYTHON:-python3}"
UNIT="${HOME}/.config/systemd/user/pdf2zh.service"
CORE="$ROOT/qyunslation/server/core.py"
IMG="$ROOT/qyunslation/extensions/image_translate.py"
WF="$ROOT/qyunslation/workflow/image_overlay_workflow.py"

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

check "left-dock 补丁存在" test -f "$ROOT/scripts/apply-pdf2zh-left-dock.py"
check "office-route 补丁存在" test -f "$ROOT/scripts/apply-pdf2zh-office-route.py"
check "service 含 left-dock" grep -q 'apply-pdf2zh-left-dock.py' "$ROOT/scripts/pdf2zh.service"
check "user unit 含 left-dock" grep -q 'apply-pdf2zh-left-dock.py' "$UNIT"
check "gui 含 dock css" grep -q '_qy_left_dock_css' "$GUI"
check "gui 含 sticky" grep -q 'position: sticky' "$GUI"
check "sidecar helper 唯一定义" bash -c 'c=$(grep -c "async def _qy_run_office_sidecar_task(" "'"$GUI"'"); test "$c" = 1'
check "lang map 存在" grep -q '_QY_LANG_TO_SIDECAR' "$GUI"
check "call site 传 to_lang" grep -q 'to_lang=ui_inputs.get("lang_to")' "$GUI"
check "payload 用 mapped" grep -q 'to_lang": mapped' "$GUI"
check "image_translate 无 del to_lang" bash -c '! grep -q "del to_lang" "'"$IMG"'"'
check "image_translate prompt 变量" grep -q 'Translate each numbered line to {target}' "$IMG"
check "ImageOverlayConfig 有 to_lang" grep -q 'to_lang: str' "$WF"
check "core 构造传 to_lang" grep -q 'to_lang=payload.to_lang' "$CORE"
check "app FileType 含 image" grep -q '"image"' "$ROOT/qyunslation/app.py"
check "MEDIA_TYPES 含 image" grep -q '"image":' "$CORE"
check "gui 语法" /home/dev/.local/share/uv/tools/pdf2zh-next/bin/python -m py_compile "$GUI"
check "office-route 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-office-route.py' 2>&1 | grep -qE 'already patched|patched:'"
check "left-dock 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-left-dock.py' 2>&1 | grep -qE 'already patched|patched:'"
check "pdf2zh 服务 active" systemctl --user is-active pdf2zh.service
check "office 服务 active" systemctl --user is-active qyunslation-office.service

STRUCT_OK=0
ROOT_PATH="$ROOT" GUI_PATH="$GUI" "$PY" - <<'PY' && STRUCT_OK=1
from pathlib import Path
import os, re, ast
root = Path(os.environ["ROOT_PATH"])
core = (root / "qyunslation/server/core.py").read_text(encoding="utf-8")
# ImageOverlay export must not be nested under DocxExportable branch as elif
# Find the export map section
idx = core.find("def _build_export_map")
assert idx >= 0
section = core[idx : idx + 2500]
# After DocxExportable block there should be independent `if isinstance(workflow, ImageOverlayWorkflow)`
assert "if isinstance(workflow, ImageOverlayWorkflow):" in section
# Must not be `elif isinstance(workflow, ImageOverlayWorkflow)` after DocxWorkflow
assert "elif isinstance(workflow, ImageOverlayWorkflow)" not in section
# DocxExportable block should not contain ImageOverlay
docx_if = section.find("if isinstance(workflow, DocxExportable):")
assert docx_if >= 0
# Find next top-level `if isinstance` after DocxExportable at same indent in the function body
# Simpler: the image if should appear after the DocxExportable block closes
img_if = section.find("if isinstance(workflow, ImageOverlayWorkflow):")
assert img_if > docx_if
# Between docx_if and img_if there should be DocxWorkflow handling but ImageOverlay must not be elif of DocxExportable
between = section[docx_if:img_if]
assert "elif isinstance(workflow, ImageOverlayWorkflow)" not in between

gui = Path(os.environ["GUI_PATH"]).read_text(encoding="utf-8")
assert gui.count("async def _qy_run_office_sidecar_task(") == 1
cs = gui.find('custom_css = """')
c0 = cs + len('custom_css = """')
m = re.search(r'\n[ \t]*"""', gui[c0:])
css = gui[c0 : c0 + m.start()]
assert "/* _qy_adv_options_css */" in css
assert "/* _qy_left_dock_css */" in css
assert css.find("/* _qy_left_dock_css */") > css.find("/* _qy_adv_options_css */")
assert "position: sticky" in css
print("ok")
PY

if [[ "$STRUCT_OK" -eq 1 ]]; then
  echo "PASS: export_map 与 CSS 结构"
  pass=$((pass + 1))
else
  echo "FAIL: export_map 与 CSS 结构"
  fail=$((fail + 1))
fi

echo "verify-plan-019: $pass/$((pass + fail))"
test "$fail" -eq 0

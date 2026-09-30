#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-020 验收：预览载荷、术语表编码、看门狗、no-store、吸底 JS。
set -uo pipefail

GUI=/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py
PY=/home/dev/.local/share/uv/tools/pdf2zh-next/bin/python
SCRIPTS=/home/dev/qyunslation/scripts
FAIL=0

check() {
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  ok    %s\n' "$desc"
  else
    printf '  FAIL  %s\n' "$desc"
    FAIL=$((FAIL + 1))
  fi
}

has() { grep -qF "$2" "$1"; }
hasnt() { ! grep -qF "$2" "$1"; }
count_is() { [ "$(grep -cF "$2" "$1")" = "$3" ]; }
count_re_is() { [ "$(grep -cE "$2" "$1")" = "$3" ]; }

echo "== 1. 预览走文件 URL，不再内联 base64 =="
check "helper _qy_file_url 唯一" count_is "$GUI" "def _qy_file_url(" 1
check "data URI 外置函数唯一" count_is "$GUI" "def _qy_externalize_data_uris(" 1
check "图片分支不再 b64encode" hasnt "$GUI" 'b64 = base64.b64encode(path.read_bytes())'
check "图片分支引用 _qy_file_url" has "$GUI" 'f'"'"'<img src="{_qy_file_url(path)}"'
check "PDF 预览走 file url iframe" has "$GUI" 'f'"'"'<iframe src="{_qy_file_url(path)}"'
check "PDF 不再交给 Gradio PDF() 空壳" hasnt "$GUI" 'return _qy_show_pdf(str(path)), gr.update(value="", visible=False)'
check "DOCX 预览外置 data URI" has "$GUI" "_qy_externalize_data_uris(_qy_docx_to_html(path)"

echo "== 2. 预览载荷实测 =="
PAYLOAD=$("$PY" - <<'PY' 2>/dev/null
from pathlib import Path
import tempfile
from pdf2zh_next import gui

img = Path(tempfile.gettempdir()) / "_qy_verify_020.png"
# 1x1 PNG 后跟 200KB 填充，确保 base64 方案会显著超标
img.write_bytes(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6300010000050001"
    )
    + b"\0" * 200_000
)
_, html = gui._qy_preview_payload(str(img))
val = html.get("value") if isinstance(html, dict) else getattr(html, "value", "")
img.unlink(missing_ok=True)
print(len(val or ""))
PY
)
check "200KB 图片预览载荷 < 2KB（实测 ${PAYLOAD:-NA}）" test "${PAYLOAD:-999999}" -lt 2048
check "预览载荷非空" test "${PAYLOAD:-0}" -gt 100

echo "== 3. 术语表编码兜底 =="
check "解码 helper 唯一" count_is "$GUI" "def _qy_decode_glossary_bytes(" 1
check "无裸 chardet.detect(file)" hasnt "$GUI" 'chardet.detect(file)["encoding"]'
check "next(csvreader) 已带默认值" hasnt "$GUI" "next(csvreader)  # Skip header"
check "解析失败会抛 gr.Error" has "$GUI" '术语表解析失败'
"$PY" - <<'PY' >/dev/null 2>&1
from pdf2zh_next import gui
import gradio as gr

# 空文件必须给出明确提示
try:
    gui._qy_decode_glossary_bytes(b"")
except gr.Error:
    pass
else:
    raise SystemExit(1)

# 任意字节都不得再冒出 TypeError / StopIteration（本次故障的原始形态）
for payload in (b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x01", b"\xff" * 64, "源,译\na,b\n".encode("gb18030")):
    try:
        out = gui._qy_decode_glossary_bytes(payload)
    except gr.Error:
        continue
    if not isinstance(out, str):
        raise SystemExit(1)
raise SystemExit(0)
PY
check "空文件报错、任意字节不再抛 TypeError" test $? -eq 0

echo "== 4. 前端看门狗 =="
check "看门狗 JS 唯一" count_re_is "$GUI" '// _qy_stale_guard_js$' 1
check "结束标记唯一" count_is "$GUI" "_qy_stale_guard_js_end" 1
check "stale guard fetch 包装未重复" bash -c \
  "sed -n '/^[[:space:]]*\/\/ _qy_stale_guard_js$/,/^[[:space:]]*\/\/ _qy_stale_guard_js_end$/p' \"$GUI\" | grep -cF 'var origFetch = window.fetch;' | grep -qx 1"
check "app_id 漂移检测存在" has "$GUI" "cfg.app_id !== APP_ID"
check "看门狗样式唯一" count_is "$GUI" "/* _qy_stale_guard_css */" 1

echo "== 5. no-store 中间件 =="
check "中间件唯一" count_is "$GUI" "class _QyNoStoreMiddleware(" 1
check "app_kwargs 挂满 6 处 launch" count_is "$GUI" "app_kwargs=_QY_APP_KWARGS," 6
check "Cache-Control 为 no-store" has "$GUI" "no-store, no-cache, must-revalidate"

echo "== 6. 吸底 JS 不再全局重排 =="
check "已改用 ResizeObserver" has "$GUI" "qyDockRO = new ResizeObserver("
check "移除 400ms 轮询" hasnt "$GUI" "setInterval(qyUpdateDockHeight, 400)"
check "移除 body MutationObserver（吸底）" hasnt "$GUI" "new MutationObserver(qyUpdateDockHeight)"

echo "== 7. 空态提示可被隐藏（嵌套 :has 非法会整条丢弃规则）=="
check "无非法嵌套 :has" test "$(grep -cE ':has\([^)]*:has\(' "$GUI")" -eq 0
check "已改为后代组合器" has "$GUI" ":has(> .pdf-preview-fixed:not(.hidden) canvas)"
check "保留合法的 :not(:has())" has "$GUI" ".pdf-preview-fixed:not(:has(canvas))"

echo "== 8. 补丁链幂等 + 语法 =="
for s in preview-url stale-guard glossary-encoding no-store css-has-fix left-dock; do
  /usr/bin/python3 "$SCRIPTS/apply-pdf2zh-$s.py" >/dev/null 2>&1
  OUT=$(/usr/bin/python3 "$SCRIPTS/apply-pdf2zh-$s.py" 2>&1)
  case "$OUT" in
    *"already patched"*) printf '  ok    %s 幂等\n' "$s" ;;
    *) printf '  FAIL  %s 非幂等: %s\n' "$s" "$OUT"; FAIL=$((FAIL + 1)) ;;
  esac
done
check "gui.py 语法可编译" "$PY" -c "import pathlib; compile(pathlib.Path('$GUI').read_text(), '$GUI', 'exec')"

echo
if [ "$FAIL" -eq 0 ]; then
  echo "PLAN-020 verify: PASS"
else
  echo "PLAN-020 verify: FAIL ($FAIL)"
fi
exit "$FAIL"

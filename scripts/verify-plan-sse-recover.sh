#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# SSE 断连修复验收：插图 executor、recover 路由、Caddy SSE flush。
set -uo pipefail

GUI=/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py
CADDY=/home/dev/qyunsgen/config/Caddyfile-production-public
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

echo "== 1. 插图翻译 run_in_executor =="
check "imgtr executor" grep -q '_qy_img_task = _qy_aio_img.get_event_loop().run_in_executor' "$GUI"
check "imgtr await" grep -q 'await _qy_img_task' "$GUI"

echo "== 2. SSE recover =="
check "recover helper" grep -q '_qy_write_recover_manifest' "$GUI"
check "recover middleware" grep -q '_qy_sse_recover_mw' "$GUI"
check "no demo routes" grep -qv '@demo.app.get("/qy/recover/{session_id}")' "$GUI"
check "recover js" grep -q '_qy_sse_recover_js' "$GUI"
check "service hook" grep -q 'apply-pdf2zh-sse-recover.py' "$SCRIPTS/pdf2zh.service"

echo "== 3. Caddy SSE =="
check "gradio sse matcher" grep -q '@gradio_sse path /gradio_api/queue/data /queue/data /gradio_api/heartbeat/*' "$CADDY"
check "flush_interval -1" grep -A6 '@gradio_sse' "$CADDY" | grep -q 'flush_interval -1'

echo "== 3b. unload grace =="
check "grace seconds" grep -q '_UNLOAD_GRACE_SECONDS = 90' "$GUI"
check "revoke unload cancel" grep -q '_revoke_unload_cancel' "$GUI"
check "scheduling cancel log" grep -q 'scheduling cancel in' "$GUI"
check "throughput idempotent" sh -c "python3 '$SCRIPTS/apply-pdf2zh-throughput.py' 2>&1 | grep -q 'already patched'"

echo "== 4. 补丁幂等 =="
python3 "$SCRIPTS/apply-pdf2zh-docimg.py" >/tmp/qy_sse_docimg.out
check "docimg idempotent" grep -q 'already patched' /tmp/qy_sse_docimg.out
python3 "$SCRIPTS/apply-pdf2zh-sse-recover.py" >/tmp/qy_sse_recover.out
check "recover idempotent" grep -q 'already patched' /tmp/qy_sse_recover.out

if [ "$FAIL" -eq 0 ]; then
  echo "PASS ($FAIL failures)"
else
  echo "FAIL ($FAIL failures)"
fi
exit "$FAIL"

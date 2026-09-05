#!/usr/bin/env bash
# verify-plan-014.sh — Office/DOCX HTML 预览
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUI="${PDF2ZH_GUI:-/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py}"
PY="${PYTHON:-python3}"
SAMPLE="${QY_OFFICE_SAMPLE:-/home/dev/pdf2zh/office_out/Meeting questions_19May2026_translated.docx}"

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

check "apply-pdf2zh-office-preview.py" test -f "$ROOT/scripts/apply-pdf2zh-office-preview.py"
check "pdf2zh.service 含 preview 补丁" grep -q 'apply-pdf2zh-office-preview.py' "$ROOT/scripts/pdf2zh.service"
check "gui 含 _qy_office_preview" grep -q '_qy_office_preview' "$GUI"
check "gui 含 preview_html" grep -q 'preview_html = gr.HTML' "$GUI"
check "gui update_preview 调 _qy_preview_payload" grep -q '_qy_preview_payload(preview_path)' "$GUI"
check "gui 译后刷新 then" grep -q '_qy_office_preview_then' "$GUI"
check "office-route 下载 html" grep -q 'PLAN-014: 旁路下载 HTML' "$GUI"
check "gui 语法" /home/dev/.local/share/uv/tools/pdf2zh-next/bin/python -m py_compile "$GUI"
check "apply 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-office-preview.py' 2>&1 | grep -qE 'already patched|patched:'"
check "office-route 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-office-route.py' 2>&1 | grep -qE 'already patched|patched:'"

if test -f "$SAMPLE"; then
  check "mammoth 可转样例 docx" bash -c "
/home/dev/qyunslation/.venv/bin/python -c \"
from pathlib import Path
from io import BytesIO
import mammoth
h=mammoth.convert_to_html(BytesIO(Path('$SAMPLE').read_bytes())).value
assert len(h) > 100
\"
"
else
  echo "SKIP: 无样例 docx ($SAMPLE)"
fi

check "pdf2zh 服务 active" systemctl --user is-active pdf2zh.service
check "office sidecar :8010" curl -fsS -o /dev/null --max-time 5 http://127.0.0.1:8010/

echo "verify-plan-014: $pass/$((pass + fail))"
test "$fail" -eq 0

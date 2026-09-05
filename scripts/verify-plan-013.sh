#!/usr/bin/env bash
# verify-plan-013.sh — 落库修复 + md/docx 导出 + 下载区精简
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VAULT="${PDF2ZH_VAULT_ROOT:-/home/dev/Targets/vault}"
TRANS_DIR="${PDF2ZH_VAULT_TRANSLATIONS_DIR:-10-Source-Documents/Translations}"
API="${QYUNSVAULT_API:-http://127.0.0.1:6201}"
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

echo "== PLAN-013a 落库 =="
check "GroupStateDB 长连接" grep -q '长连接' "$ROOT/scripts/pdf2zh-archive-watch.py"
check "index_db 用 closing" grep -q 'contextlib' "$ROOT/qyunslation/archive/index_db.py" || grep -q 'closing' "$ROOT/qyunslation/archive/index_db.py"
check "letter-mono 分组" bash -c "cd '$ROOT' && PYTHONPATH=. $PY -c \"from qyunslation.archive.pdf2zh_ingest import output_group_key as g; assert g('x.hpd-ocr.letter-mono.pdf')=='x'\""
check "zh.md 分组" bash -c "cd '$ROOT' && PYTHONPATH=. $PY -c \"from qyunslation.archive.pdf2zh_ingest import output_group_key as g; assert g('doc.zh.md')=='doc'\""
check "service LimitNOFILE" grep -q 'LimitNOFILE=4096' "$ROOT/scripts/pdf2zh-archive-watch.service"
check "Vault 有 DT-0016+ 新条目" bash -c "ls '$VAULT/$TRANS_DIR'/DT-2026-001*.md 2>/dev/null | head -1 | grep -q ."
check "watcher 在跑" systemctl --user is-active pdf2zh-archive-watch.service

if systemctl --user is-active pdf2zh-archive-watch.service >/dev/null 2>&1; then
  pid=$(systemctl --user show pdf2zh-archive-watch -p MainPID --value)
  nfd=$(ls "/proc/$pid/fd" 2>/dev/null | wc -l)
  if [ "$nfd" -lt 200 ]; then
    echo "PASS: watcher fd=$nfd (<200)"
    pass=$((pass + 1))
  else
    echo "FAIL: watcher fd=$nfd (疑似泄漏)"
    fail=$((fail + 1))
  fi
fi

echo "== PLAN-013b 导出 =="
check "debug2md.py" test -f "$ROOT/scripts/debug2md.py"
check "export_md_docx.py" test -f "$ROOT/scripts/export_md_docx.py"
check "ConverterHpd" test -f "$ROOT/qyunslation/converter/x2md/converter_hpd.py"
check "workflow 注册 hpd" grep -q '_ensure_hpd_factory' "$ROOT/qyunslation/workflow/md_based_workflow.py"
check "types 含 hpd" grep -q '"hpd"' "$ROOT/qyunslation/exporter/md/types.py"

echo "== PLAN-013c UI =="
check "apply-pdf2zh-downloads.py" test -f "$ROOT/scripts/apply-pdf2zh-downloads.py"
check "pdf2zh.service 含 downloads 补丁" grep -q 'apply-pdf2zh-downloads.py' "$ROOT/scripts/pdf2zh.service"
check "gui 已打 downloads 标记" grep -q '_qy_downloads_ui' "$GUI"
check "gui 有仅译稿选项" grep -q 'Translation only' "$GUI"
check "apply 幂等" bash -c "$PY '$ROOT/scripts/apply-pdf2zh-downloads.py' 2>&1 | grep -qE '已是|已含|已写入|downloads'"

echo "== PLAN-013d Vault =="
check "vault 笔记含 original_storage_key" grep -q 'original_storage_key' "$ROOT/qyunslation/archive/pdf2zh_vault.py"
check "vault 笔记优先 translated_md" grep -q 'translated_md' "$ROOT/qyunslation/archive/pdf2zh_vault.py"
check "DT-0016 正文来自 md" bash -c "grep -q 'body_source: translated_md' '$VAULT/$TRANS_DIR'/DT-2026-0016-*.md"
check "qyunsvault-api health" curl -fsS -o /dev/null --max-time 8 "$API/api/health"
check "向量检索可命中翻译" bash -c "
$PY -c \"
import json, urllib.parse, urllib.request
q=urllib.parse.urlencode({'q':'FDA PIND 会议初步意见','mode':'hybrid','top_k':'8'})
with urllib.request.urlopen('$API/api/v1/search?'+q, timeout=120) as r:
    data=json.load(r)
items=data.get('items') or []
ok=any('10-Source-Documents/Translations' in (it.get('source') or '') for it in items)
raise SystemExit(0 if ok else 1)
\""

echo "verify-plan-013: $pass/$((pass + fail))"
test "$fail" -eq 0

#!/usr/bin/env bash
# verify-plan-002f.sh — pdf2zh Vault 入库 + 向量检索断言
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VAULT="${PDF2ZH_VAULT_ROOT:-/home/dev/Targets/vault}"
TRANS_DIR="${PDF2ZH_VAULT_TRANSLATIONS_DIR:-10-Source-Documents/Translations}"
API="${QYUNSVAULT_API:-http://127.0.0.1:6201}"

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

check "Vault 翻译目录存在" test -d "$VAULT/$TRANS_DIR"
check "至少一条 DT- 翻译笔记" bash -c "ls '$VAULT/$TRANS_DIR'/DT-*.md 2>/dev/null | head -1 | grep -q ."
check "qyunsvault-api health" curl -fsS -o /dev/null --max-time 8 "$API/api/health"
check "向量检索可命中翻译笔记" python3 -c "
import json, urllib.parse, urllib.request
q=urllib.parse.urlencode({'q':'PDF 保留排版 pdf2zh','mode':'hybrid','top_k':'5'})
with urllib.request.urlopen('$API/api/v1/search?'+q, timeout=120) as r:
    data=json.load(r)
items=data.get('items') or []
ok=any('10-Source-Documents/Translations' in (it.get('source') or '') for it in items)
raise SystemExit(0 if ok else 1)
"

echo "verify-plan-002f: $pass/$((pass + fail))"
test "$fail" -eq 0

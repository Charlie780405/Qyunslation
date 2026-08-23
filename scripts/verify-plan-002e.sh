#!/usr/bin/env bash
# verify-plan-002e.sh — pdf2zh MinIO 旁路归档断言
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${PDF2ZH_ARCHIVE_ENV:-/home/dev/pdf2zh/archive.env}"
INDEX_DB="/home/dev/pdf2zh/archive/index.db"

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

check "PLAN-002e 文档存在" test -f "$ROOT/docs/plans/PLAN-002-babeldoc-replace-translate/PLAN-002e-pdf2zh-archive.md"
check "archive.env 存在" test -f "$ENV_FILE"
check "watcher unit 已安装" test -f "$HOME/.config/systemd/user/pdf2zh-archive-watch.service"
check "watcher active" systemctl --user is-active pdf2zh-archive-watch.service
check "MinIO health" curl -fsS -o /dev/null --max-time 5 http://127.0.0.1:9002/minio/health/live
check "索引库存在" test -f "$INDEX_DB"
check "索引有 pdf2zh 记录" python3 -c "import sqlite3; c=sqlite3.connect('$INDEX_DB').execute(\"SELECT COUNT(*) FROM archives WHERE workflow_type='pdf2zh'\").fetchone()[0]; raise SystemExit(0 if c>0 else 1)"

echo "verify-plan-002e: $pass/$((pass + fail))"
test "$fail" -eq 0

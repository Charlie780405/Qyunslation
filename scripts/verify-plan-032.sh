#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-032 归档卫生门：文件名清洗 + 编号前缀。不嵌套其它 PLAN 门。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-900}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT

cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }

show_failure_log() { [[ -f "$1" ]] && tail -n 60 "$1"; }

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then pass "$label"
  else fail "$label"; show_failure_log "$log_path"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

run_pass "PLAN-032 modules compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/archive/filenames.py \
    qyunslation/archive/pdf2zh_ingest.py \
    qyunslation/archive/index_db.py \
    scripts/office-archive-watch.py \
    scripts/fix-archive-filenames.py

run_pass "archive filename + id tests" "$STAGE_DIR/archive.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/test_pdf2zh_archive.py

run_pass "new archive ids use QY- prefix" "$STAGE_DIR/prefix.log" \
  "$PY" - <<'PY'
import tempfile
from pathlib import Path

from qyunslation.archive.index_db import ArchiveIndex, is_archive_id

with tempfile.TemporaryDirectory() as tmp:
    index = ArchiveIndex(Path(tmp) / "index.db")
    allocated = index.allocate_id()

assert allocated.startswith("QY-"), allocated
# 历史前缀仍须被认作合法编号
assert is_archive_id("DT-2026-0001")
assert is_archive_id(allocated)
assert not is_archive_id("random-2026-0001")
PY

run_pass "office watcher records the uploaded name, not the product name" "$STAGE_DIR/office.log" \
  "$PY" - <<'PY'
from qyunslation.archive.filenames import original_filename_from_product

assert original_filename_from_product("x_translated.docx") == "x.docx"
assert original_filename_from_product("y.zh.jpg") == "y.jpg"
PY

run_pass "existing-record repair script stays dry-run by default" "$STAGE_DIR/dryrun.log" \
  "$PY" - <<'PY'
import ast
from pathlib import Path

source = Path("scripts/fix-archive-filenames.py").read_text(encoding="utf-8")
tree = ast.parse(source)
# --apply 必须是显式 store_true，缺省不得写库
assert '"--apply"' in source and 'action="store_true"' in source
assert "shutil.copy2" in source, "apply 前必须备份"
PY

# 全量套件必须 0 failed：PLAN-032 的目的就是消灭「3 个既有失败」基线
FULL_LOG="$STAGE_DIR/full.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests --no-cov >"$FULL_LOG" 2>&1; then
  pass "full suite has no failures"
else
  fail "full suite still has failures"
  show_failure_log "$FULL_LOG"
fi

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1

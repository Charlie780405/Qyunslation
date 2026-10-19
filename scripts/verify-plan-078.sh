#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-078：翻译工作台 QA 处理闭环、参数确认、任务管理与效率专项的收尾总门禁。
# 三态：PASS / FAIL / BLOCKED（缺少浏览器证据等无法自动验证的项标 BLOCKED，不当作通过）。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
PLAN="docs/plans/PLAN-078-workbench-qa-task-experience"
LOGDIR="${QYUNSLATION_VERIFY_LOG_DIR:-${TMPDIR:-/tmp}}"
FAILURES=0
BLOCKED=0
pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

# 1) 文档与关键产物存在
REQUIRED=(
  "$PLAN/README.md"
  "$PLAN/PLAN-078-workbench-qa-task-experience.md"
  "$PLAN/PLAN-078a-state-consistency-qa-diagnosis.md"
  "$PLAN/PLAN-078b-qa-resolution-loop.md"
  "$PLAN/PLAN-078c-run-parameter-confirmation.md"
  "$PLAN/PLAN-078d-run-search-and-management.md"
  "$PLAN/PLAN-078e-batch-and-recycle-bin.md"
  "$PLAN/PLAN-078f-efficiency-reliability.md"
  "docs/walkthroughs/WT-078-workbench-qa-task-experience.md"
  "scripts/plan078-qa-diagnose.py"
  "scripts/plan078-qa-replay.py"
  "scripts/plan078e-purge-expired.py"
  "scripts/plan078e-trash-to-archive.py"
  "qyunslation/pipeline/preflight_probe.py"
  "alembic/versions/078a0001_gated_status_backfill.py"
  "alembic/versions/078a0002_qa_check_round.py"
  "alembic/versions/078b0001_qa_resolution.py"
  "alembic/versions/078d0001_run_name_version.py"
  "alembic/versions/078e0001_run_trash_and_batch.py"
)
for path in "${REQUIRED[@]}"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

# 2) 子计划状态行不能还写“未实施”
for sub in a b c d e f; do
  file=$(ls "$ROOT/$PLAN"/PLAN-078${sub}-*.md 2>/dev/null | head -1)
  if [[ -n "$file" ]] && sed -n '3p' "$file" | grep -q "未实施"; then
    fail "078${sub} 状态行仍写“未实施”"
  elif [[ -n "$file" ]]; then
    pass "078${sub} 状态行已更新"
  fi
done

# 3) 后端：所有 PLAN-078 的专项测试 + 相邻回归
if [[ -x "$PY" ]]; then
  mapfile -t TESTS < <(cd "$ROOT" && ls tests/*/test_plan078*.py tests/api/test_term_enrich_suggestions.py tests/api/test_plan071e_real_qa_gate.py 2>/dev/null)
  if [[ "${#TESTS[@]}" -gt 0 ]] && (cd "$ROOT" && "$PY" -m pytest -q -o addopts= -p no:cacheprovider "${TESTS[@]}" >"$LOGDIR/verify-plan-078-backend.log" 2>&1); then
    pass "PLAN-078 backend tests (${#TESTS[@]} files)"
  else
    fail "PLAN-078 backend tests (see $LOGDIR/verify-plan-078-backend.log)"
  fi
else
  blocked "Python interpreter unavailable"
fi

# 4) 前端：vitest（含 axe）+ 构建
if [[ -d "$ROOT/frontend/node_modules" ]]; then
  if (cd "$ROOT/frontend" && npx vitest run src/next >"$LOGDIR/verify-plan-078-frontend.log" 2>&1); then
    pass "frontend vitest (src/next)"
  else
    fail "frontend vitest (see $LOGDIR/verify-plan-078-frontend.log)"
  fi
  if (cd "$ROOT/frontend" && npm run build >/dev/null 2>&1); then
    pass "frontend build"
  else
    fail "frontend build"
  fi
else
  blocked "frontend dependencies unavailable"
fi

# 5) 浏览器证据（拖放、触屏、三种浏览器、真实 PDF 预检卡）只能人工或另行脚本验证
# 有浏览器不等于有证据：目前没有自动化的浏览器用例，所以始终报告为未验证。
blocked "浏览器走查（H12 拖放、触屏、扫描件预检卡、轮询请求数）尚无自动化用例，仍未验证"

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED fail=0 blocked=%s\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
exit 0

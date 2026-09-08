#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-028d: portable Tier-3 correctness and performance gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-300}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKERS=0

cleanup() {
  rm -rf -- "$STAGE_DIR"
}
trap cleanup EXIT

cd "$ROOT" || exit 1

pass() {
  printf 'PASS: %s\n' "$1"
}

fail() {
  printf 'FAIL: %s\n' "$1"
  FAILURES=$((FAILURES + 1))
}

blocked() {
  printf 'BLOCKED: %s\n' "$1"
  BLOCKERS=$((BLOCKERS + 1))
}

show_failure_log() {
  local log_path="$1"
  if [[ -f "$log_path" ]]; then
    tail -n 80 "$log_path"
  fi
}

run_pass() {
  local label="$1"
  local log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then
    pass "$label"
  else
    fail "$label"
    show_failure_log "$log_path"
  fi
}

resolve_sample() {
  local explicit="${QYUNSLATION_PLAN028_SAMPLE:-}"
  local sample_root="${QYUNSLATION_SAMPLE_ROOT:-}"
  local candidate

  if [[ -n "$explicit" ]]; then
    printf '%s\n' "$explicit"
    return
  fi
  if [[ -n "$sample_root" ]]; then
    for candidate in \
      "$sample_root/nature_comm_53384.pdf" \
      "$sample_root/reference/nature_comm_53384.pdf" \
      "$sample_root/tests/fixtures/structure/reference/nature_comm_53384.pdf"; do
      if [[ -f "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return
      fi
    done
  fi
  # PLAN-030h H1：这份样本本来就在仓内，外部根里找不到时不得返回不存在的路径
  printf '%s\n' \
    "$ROOT/tests/fixtures/structure/reference/nature_comm_53384.pdf"
}

if [[ ! -x "$PY" ]]; then
  blocked "Python runtime is unavailable at $PY"
fi
if [[ ! "$TEST_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  blocked "QYUNSLATION_VERIFY_TIMEOUT_SECONDS must be a positive integer"
fi

SAMPLE="$(resolve_sample)"
if [[ ! -f "$SAMPLE" ]]; then
  blocked "PLAN-028 gold sample is unavailable at $SAMPLE"
fi

if [[ "$BLOCKERS" -ne 0 ]]; then
  printf 'SUMMARY: FAIL blocked=%d fail=%d\n' "$BLOCKERS" "$FAILURES"
  exit 1
fi

run_pass \
  "PLAN-028d modules compile" \
  "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure \
    scripts/doc_image_prescan.py \
    scripts/pdf_figure_crop.py

run_pass \
  "Tier-3 page reuse, cache, figure, table, and layout tests" \
  "$STAGE_DIR/focused.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
    "$PY" -m pytest -q --no-cov \
      tests/structure/test_tier3_page_analysis.py \
      tests/structure/test_prescan_manifest.py \
      tests/structure/test_figure_regions.py \
      tests/structure/test_table_protection.py \
      tests/structure/test_column_layout.py

BENCHMARK_LOG="$STAGE_DIR/benchmark.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  env PYTHONPATH="$SCRIPTS:$ROOT" QYUNSLATION_PLAN028_SAMPLE="$SAMPLE" \
  "$PY" - >"$BENCHMARK_LOG" 2>&1 <<'PY'
import os
import statistics
import tempfile
import time
from pathlib import Path

import pymupdf

from doc_image_prescan import scan_pdf_tier3

sample = Path(os.environ["QYUNSLATION_PLAN028_SAMPLE"])
with pymupdf.open(sample) as document:
    total_pages = len(document)
assert total_pages == 19, f"gold sample page count changed: {total_pages}"


def assert_complete(result) -> None:
    assert result.error is None, result.error
    assert result.pages_scanned == total_pages, (
        result.pages_scanned,
        total_pages,
    )
    assert result.truncated is False, result
    assert result.figure_caption_count == 7, result.figure_caption_count
    assert result.table_caption_count == 3, result.table_caption_count
    assert result.translatable_count == 7, result.translatable_count


cold_seconds = []
warm_seconds = None
with tempfile.TemporaryDirectory(prefix="plan028d-") as parent:
    for run in range(3):
        cache = Path(parent) / f"cold-{run}"
        os.environ["QYUNSLATION_MANIFEST_CACHE"] = str(cache)
        started = time.perf_counter()
        result = scan_pdf_tier3(sample)
        elapsed = time.perf_counter() - started
        assert_complete(result)
        assert elapsed < 15.0, f"cold run {run + 1} took {elapsed:.3f}s"
        cold_seconds.append(elapsed)

    started = time.perf_counter()
    warm_result = scan_pdf_tier3(sample)
    warm_seconds = time.perf_counter() - started
    assert_complete(warm_result)

median_seconds = statistics.median(cold_seconds)
assert median_seconds < 12.0, f"cold median took {median_seconds:.3f}s"
assert max(cold_seconds) < 15.0, f"cold max took {max(cold_seconds):.3f}s"
assert warm_seconds < 1.0, f"warm cache took {warm_seconds:.3f}s"
print(
    "tier3_benchmark",
    "cold=" + ",".join(f"{value:.3f}" for value in cold_seconds),
    f"median={median_seconds:.3f}",
    f"max={max(cold_seconds):.3f}",
    f"warm={warm_seconds:.3f}",
    f"pages={total_pages}",
    "counts=7/3/7",
)
PY
then
  pass "19-page Tier-3 cold and warm performance budgets"
  tail -n 1 "$BENCHMARK_LOG"
else
  fail "19-page Tier-3 cold and warm performance budgets"
  show_failure_log "$BENCHMARK_LOG"
fi

if [[ "$FAILURES" -eq 0 && "$BLOCKERS" -eq 0 ]]; then
  printf 'SUMMARY: PASS blocked=0 fail=0\n'
  exit 0
fi

printf 'SUMMARY: FAIL blocked=%d fail=%d\n' "$BLOCKERS" "$FAILURES"
exit 1

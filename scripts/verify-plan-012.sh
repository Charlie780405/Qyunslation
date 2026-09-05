#!/usr/bin/env bash
# verify-plan-012.sh — 扫描书信叠字/字号/并行/进度
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-python3}"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
SKILL="$ROOT/.cursor/skills/scanned-doc-layout-fidelity/SKILL.md"
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
echo "== PLAN-012 verify =="
check "letter_pipeline.py" test -f "$ROOT/scripts/letter_pipeline.py"
check "unit letter_pipeline" "$PY" -m unittest scripts.test_letter_pipeline
check "unit kv_reinsert" "$PY" -m unittest scripts.test_kv_reinsert
check "unit graphic_regions" "$PY" -m unittest scripts.test_graphic_regions
check "正文锁 12pt" grep -q '_BODY_BASE = 12.0' "$ROOT/scripts/kv_reinsert.py"
check "无 13pt 升号" bash -c "! grep -q '_BODY_AIRY' '$ROOT/scripts/kv_reinsert.py'"
check "reinsert kinds" grep -q 'kinds: set\[str\] | None' "$ROOT/scripts/graphic_reinsert.py"
check "letter 只 logo/stamp" grep -q '{"logo", "stamp"}' "$ROOT/scripts/letter_pipeline.py"
check "原始盒擦除" grep -q 'raw_boxes' "$ROOT/scripts/hpd_ocr.py"
check "细长带过滤" grep -q 'aspect > 5.0' "$ROOT/scripts/graphic_regions.py"
check "OCR async 补丁" grep -q '_qy_aio_ocr' "$ROOT/scripts/apply-pdf2zh-docprofile.py"
check "软失败 warnings" grep -q 'warnings.json' "$ROOT/scripts/letter_pipeline.py"
check "Skill 铁律 13 回插" grep -q '只限 logo / stamp' "$SKILL"
check "Skill 铁律 14 原始盒" grep -q '原始 OCR 盒' "$SKILL"
check "Skill 铁律 17 executor" grep -q 'run_in_executor' "$SKILL"
check "apply 幂等" "$PY" "$ROOT/scripts/apply-pdf2zh-docprofile.py"
check "gui 可解析" "$PY" -c "import ast; ast.parse(open(r'$GUI').read())"
check "gui OCR async" grep -q '_qy_aio_ocr' "$GUI"
check "gui letter hook" grep -q '_qy_letter_reflow' "$GUI"
echo "verify-plan-012: $pass/$((pass + fail))"
[[ "$fail" -eq 0 ]]

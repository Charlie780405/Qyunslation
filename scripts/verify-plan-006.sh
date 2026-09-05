#!/usr/bin/env bash
# verify-plan-006.sh — PLAN-006 审核整治验收
# 用法: bash scripts/verify-plan-006.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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

echo "== PLAN-006 documents =="
check "PLAN-006 纲领" test -f "$ROOT/docs/plans/PLAN-006-audit-remediation/PLAN-006-audit-remediation.md"
check "baseline-006b" test -f "$ROOT/docs/perf/baseline-006b.json"
check "baseline-006c" test -f "$ROOT/docs/perf/baseline-006c.json"
check "benchmark script" test -f "$ROOT/scripts/benchmark-plan-006c.py"
check "pytest workflow" test -f "$ROOT/.github/workflows/pytest.yml"

echo "== package rename =="
check "no docutranslate symlink" test ! -e "$ROOT/docutranslate"
check "pyproject name=qyunslation" grep -q 'name = "qyunslation"' "$ROOT/pyproject.toml"
check "no import docutranslate in py" bash -c '! rg -q "^(from|import) docutranslate" -g "*.py" --glob "!.venv" --glob "!htmlcov" --glob "!archive"'
check "import qyunslation" .venv/bin/python -c "import qyunslation; assert qyunslation.__version__"
check "CLI help" bash -c '.venv/bin/qyunslation --help | head -1'

echo "== config =="
check "CONCURRENT=8 in .env" grep -q 'DOCUTRANSLATE_CONCURRENT=8' "$ROOT/.env"
check "TIMEOUT=300 in .env" grep -q 'DOCUTRANSLATE_TIMEOUT=300' "$ROOT/.env"
check "config dual-read concurrent" .venv/bin/python -c "from qyunslation.config import CONCURRENT; assert CONCURRENT==8"
check "TLS_VERIFY default True" .venv/bin/python -c "from qyunslation.config import TLS_VERIFY; assert TLS_VERIFY is True"

echo "== security / defects =="
check "ConverterDoclingConfig split" test -f "$ROOT/qyunslation/converter/x2md/converter_docling_config.py"
check "Zip Slip helper" grep -q '_safe_extractall' "$ROOT/qyunslation/extensions/image_replace.py"
check "API token middleware" grep -q 'optional_api_token_auth' "$ROOT/qyunslation/app.py"
check "task_id 16 hex" grep -q 'hex\[:16\]' "$ROOT/qyunslation/app.py"
check "image_overlay to_thread" grep -q 'asyncio.to_thread' "$ROOT/qyunslation/workflow/image_overlay_workflow.py"
check "cacher lock" grep -q 'threading.Lock' "$ROOT/qyunslation/cacher/md_based_convert_cacher.py"
check "custom_api package import" grep -q 'qyunslation.extensions.glossary_db' "$ROOT/qyunslation/custom_api.py"
check "enhanced_translate archived" test -f "$ROOT/archive/legacy/enhanced_translate.py"
check "no orphan translation_cache" test ! -f "$ROOT/translation_cache.json"

echo "== import speed =="
IMPORT_S=$(/usr/bin/time -f '%e' .venv/bin/python -c "from qyunslation.app import app" 2>&1 | tail -1)
python3 - <<PY
s=float("$IMPORT_S")
print(f"import app: {s:.2f}s")
raise SystemExit(0 if s < 8.0 else 1)
PY
if [[ $? -eq 0 ]]; then
  echo "PASS: import app < 8s ($IMPORT_S)"
  pass=$((pass + 1))
else
  echo "FAIL: import app too slow ($IMPORT_S)"
  fail=$((fail + 1))
fi

echo "== pytest smoke =="
if .venv/bin/python -m pytest tests/test_glossary_db.py tests/test_custom_api.py tests/test_app.py -q --no-cov 2>&1 | tee /tmp/verify-006-pytest.log | tail -5; then
  echo "PASS: targeted pytest"
  pass=$((pass + 1))
else
  echo "FAIL: targeted pytest"
  fail=$((fail + 1))
fi

echo
echo "RESULT: pass=$pass fail=$fail"
[[ "$fail" -eq 0 ]]

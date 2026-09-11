#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-044 regulatory layout normalize + delivery rate gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  PY="$ROOT/.venv/bin/python"
fi
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

run_pass() {
  local label="$1" log="$2"
  shift 2
  if "$@" >"$log" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=0 fail=1\n'
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-044-regulatory-layout-normalize"
[[ -f "$PLAN_DIR/PLAN-044-regulatory-layout-normalize.md" ]] \
  && pass "PLAN-044 charter" || fail "missing PLAN-044 charter"

grep -q 'compose_cell_text' "$ROOT/qyunslation/structure/table_structure.py" \
  && pass "044a compose_cell_text" || fail "044a missing"
grep -q 'TABLE_CELL_DEGRADED' "$ROOT/qyunslation/structure/table_qc.py" \
  && pass "044c TABLE_CELL_DEGRADED" || fail "044c missing"
grep -q 'TABLE_ROLE_SIZE' "$ROOT/qyunslation/structure/role_fitter.py" \
  && pass "044d TABLE_ROLE_SIZE" || fail "044d missing"
grep -q 'normalize_table_sizes' "$ROOT/scripts/pdf_table_translate.py" \
  && pass "044d normalize wired" || fail "044d not wired"
grep -q '单条补译\|缺索引' "$ROOT/scripts/pdf_table_translate.py" \
  && pass "044b batch retry" || fail "044b missing"

run_pass "044 compile" "$STAGE_DIR/compile.log" "$PY" -m compileall -q \
  qyunslation/structure/table_structure.py \
  qyunslation/structure/table_qc.py \
  qyunslation/structure/table_translate.py \
  qyunslation/structure/role_fitter.py \
  qyunslation/structure/table_writeback.py \
  scripts/pdf_table_translate.py

run_pass "044 focused tests" "$STAGE_DIR/tests.log" \
  timeout --signal=INT --kill-after=10s 180s "$PY" -m pytest -q -o addopts= \
    tests/structure/test_plan044_cell_compose.py \
    tests/structure/test_plan044_quality.py \
    tests/structure/test_plan041_quality_gates.py \
    tests/structure/test_plan043_quality.py

SAMPLE="${QYUNSLATION_PLAN044_SAMPLE:-}"
if [[ -z "$SAMPLE" || ! -f "$SAMPLE" ]]; then
  blocked "sample missing (set QYUNSLATION_PLAN044_SAMPLE to 611-3期.pdf)"
else
  if SAMPLE="$SAMPLE" "$PY" - <<'PY'
import os, re, sys
from collections import Counter
from qyunslation.structure.scan_pdf import PdfStructureScanner
from qyunslation.structure.models import ObjectType, ContentProfile
from qyunslation.structure.table_structure import compose_cell_text

path = os.environ["SAMPLE"]
m = PdfStructureScanner().scan(path)
profile = m.document.content_profile
tabs = [o for o in m.objects if o.type is ObjectType.TABLE]
n_blocks = sum(len(o.translatable_blocks or []) for o in tabs)
print(f"profile={profile} tables={len(tabs)} blocks={n_blocks}")
if profile is not ContentProfile.REGULATORY and str(profile) != "REGULATORY":
    print("FAIL: expected REGULATORY", file=sys.stderr); sys.exit(1)
# 源文噪声抽检：不应再出现「序 号」「体 格」类插空格
bad = []
for o in tabs:
    for b in o.translatable_blocks or []:
        t = b.source_text or ""
        if re.search(r"[\u4e00-\u9fff]\s+[\u4e00-\u9fff]", t) and len(t) <= 8:
            # 短格内 CJK 插空格视为 H2 残留
            if re.search(r"(序\s+号|体\s+格|用\s+药|周\s*一\s+次)", t):
                bad.append(t)
if bad:
    print("FAIL H2 samples:", bad[:8], file=sys.stderr); sys.exit(1)
# compose unit still healthy
assert compose_cell_text([(0,0,10,10,"序"),(10,0.2,20,10.2,"号")]) == "序号"
print("sample scan OK")
sys.exit(0)
PY
  then pass "044 sample scan (H2 clean)"
  else fail "044 sample scan"
  fi
fi

EN_OUT="${QYUNSLATION_PLAN044_EN_OUTPUT:-}"
if [[ -z "$EN_OUT" || ! -f "$EN_OUT" ]]; then
  blocked "EN tbltr missing (set QYUNSLATION_PLAN044_EN_OUTPUT after retranslate)"
else
  if SAMPLE="$EN_OUT" "$PY" - <<'PY'
import os, re, sys
from collections import Counter
import pymupdf

doc = pymupdf.open(os.environ["SAMPLE"])
fonts, sizes = Counter(), Counter()
tiny = total = cjk = 0
for page in doc:
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            for s in line.get("spans", []):
                t = (s.get("text") or "").strip()
                if not t:
                    continue
                total += 1
                fonts[s.get("font") or ""] += 1
                sz = round(float(s.get("size") or 0), 1)
                sizes[sz] += 1
                if float(s.get("size") or 0) < 7.0:
                    tiny += 1
                cjk += len(re.findall(r"[\u4e00-\u9fff]", t))
doc.close()
# 软门：重译后表链应大幅降低字体族与微字；此处只做方向性断言
print(f"spans={total} fonts={len(fonts)} size_tiers={len(sizes)} tiny_ratio={tiny/max(total,1):.2f} cjk={cjk}")
if len(fonts) > 4:
    print("WARN: font families still high", dict(fonts), file=sys.stderr)
if tiny / max(total, 1) > 0.25:
    print("FAIL: tiny span ratio >25%", file=sys.stderr); sys.exit(1)
print("EN output soft gate OK")
sys.exit(0)
PY
  then pass "044 EN output soft gate"
  else fail "044 EN output soft gate"
  fi
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%d blocked=%d\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%d fail=0\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
exit 0

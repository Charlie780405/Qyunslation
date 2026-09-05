#!/usr/bin/env bash
# PLAN-007a：扫描件第 1 页变体夹具
# 用法: bash scripts/bench-scanned-page1.sh [V0|V1|V2|V3|V4|all]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${QYUNSLATION_BENCH_007:-/home/dev/pdf2zh/bench/007}"
SRC="${QYUNSLATION_BENCH_SRC:-/home/dev/pdf2zh/pdf2zh_files/5fa54bcf-4843-4e97-8cd0-85c797fa9b5d/FDA responses on PIND.pdf}"
HPD_SSOT="$ROOT/scripts/hpd_ocr.py"
BABELDOC="/home/dev/.local/share/uv/tools/pdf2zh-next/bin/pdf2zh_next"
PY="/home/dev/.local/share/uv/tools/pdf2zh-next/bin/python"
GLOSSARY="/home/dev/pdf2zh/glossaries/qx027n.csv"
BASELINE="$ROOT/docs/perf/baseline-007a.json"
OLLAMA_HOST="${QYUNSLATION_OLLAMA_HOST:-http://100.67.66.123:11434}"
MODEL="${QYUNSLATION_BENCH_MODEL:-qwen3.6:35b-a3b}"

VARIANT="${1:-V0}"
mkdir -p "$WORK"

extract_page1() {
  if [[ -f "$WORK/page1.pdf" ]]; then
    echo "reuse: $WORK/page1.pdf"
    return
  fi
  "$PY" - <<PY
import pymupdf
src = pymupdf.open(r"""$SRC""")
out = pymupdf.open()
out.insert_pdf(src, from_page=0, to_page=0)
out.save(r"""$WORK/page1.pdf""")
out.close(); src.close()
print("wrote $WORK/page1.pdf")
PY
}

run_hpd() {
  local force="${1:-0}"
  if [[ "$force" != "1" && -f "$WORK/page1.hpd-ocr.pdf" && "$WORK/page1.hpd-ocr.pdf" -nt "$HPD_SSOT" ]]; then
    echo "reuse OCR: $WORK/page1.hpd-ocr.pdf"
    return
  fi
  echo "== HPD OCR =="
  QYUNSLATION_HPD_DEBUG=1 PYTHONPATH="$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}" "$PY" - <<PY
import sys
from pathlib import Path
sys.path.insert(0, r"$ROOT/scripts")
from hpd_ocr import ocr_pdf_with_hpd
dest = Path(r"$WORK/page1.hpd-ocr.pdf")
ocr_pdf_with_hpd(Path(r"$WORK/page1.pdf"), dest)
print("wrote", dest)
PY
}

variant_flags() {
  case "$1" in
    V0) echo "--skip-scanned-detection" ;;
    V1) echo "--skip-scanned-detection --ocr-workaround --disable-rich-text-translate" ;;
    V2) echo "--skip-scanned-detection --ocr-workaround --disable-rich-text-translate --primary-font-family serif" ;;
    V3) echo "--skip-scanned-detection --ocr-workaround --disable-rich-text-translate --primary-font-family serif" ;;
    V4) echo "--skip-scanned-detection --ocr-workaround --disable-rich-text-translate --primary-font-family serif --enable-json-mode-if-requested" ;;
    V5) echo "--skip-scanned-detection --ocr-workaround --disable-rich-text-translate --primary-font-family serif" ;;
    *) echo "unknown variant: $1" >&2; exit 2 ;;
  esac
}

measure_pdf_fonts() {
  local pdf="$1"
  "$PY" - <<PY
import json, statistics, re, pymupdf
d = pymupdf.open(r"""$pdf""")
pg = d[0]
sizes = []
for b in pg.get_text("dict")["blocks"]:
    for l in b.get("lines", []):
        for s in l["spans"]:
            if s.get("text", "").strip():
                sizes.append(float(s["size"]))
text = pg.get_text() or ""
cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
latin = len(re.findall(r"[A-Za-z]", text))
total = cjk + latin
cjk_ratio = (cjk / total) if total else 0.0
print(json.dumps({
    "chars": len(text.strip()),
    "font_median": statistics.median(sizes) if sizes else None,
    "font_min": min(sizes) if sizes else None,
    "font_max": max(sizes) if sizes else None,
    "cjk_ratio": round(cjk_ratio, 4),
    "cjk": cjk,
    "latin": latin,
}))
d.close()
PY
}

render_png() {
  local pdf="$1" png="$2"
  [[ -f "$pdf" ]] || return 0
  "$PY" - <<PY
import pymupdf
d = pymupdf.open(r"""$pdf""")
d[0].get_pixmap(dpi=110).save(r"""$png""")
d.close()
print("png", r"""$png""")
PY
}

run_variant() {
  local v="$1"
  local out="$WORK/out-$v"
  local flags
  flags="$(variant_flags "$v")"
  mkdir -p "$out"
  echo "== $v flags: $flags =="
  local t0 t1 elapsed
  t0=$(date +%s)
  # shellcheck disable=SC2086
  "$BABELDOC" "$WORK/page1.hpd-ocr.pdf" \
    --lang-in en --lang-out zh --output "$out" \
    --ollama --ollama-model "$MODEL" \
    --ollama-host "$OLLAMA_HOST" \
    --glossaries "$GLOSSARY" \
    --custom-system-prompt "/no_think You are a professional, authentic machine translation engine." \
    --no-auto-extract-glossary --ignore-cache --qps 4 --pool-max-workers 4 \
    --watermark-output-mode no_watermark \
    $flags 2>&1 | tee "$out/babeldoc.log"
  t1=$(date +%s)
  elapsed=$((t1 - t0))

  local mono dual
  mono="$(find "$out" -maxdepth 2 -type f -name '*.mono.pdf' -newer "$out/babeldoc.log" 2>/dev/null | head -1 || true)"
  dual="$(find "$out" -maxdepth 2 -type f -name '*.dual.pdf' -newer "$out/babeldoc.log" 2>/dev/null | head -1 || true)"
  [[ -n "$dual" ]] || dual="$(find "$out" -maxdepth 2 -type f -name '*.dual.pdf' | head -1 || true)"
  [[ -n "$mono" ]] || mono="$(find "$out" -maxdepth 2 -type f -name '*.mono.pdf' | head -1 || true)"

  # ocr_workaround 时 babeldoc 偶发 Mono PDF: None；用 dual 左半页作为译文页度量
  local measure_pdf="$mono"
  if [[ -n "$dual" && -f "$dual" ]]; then
    if [[ -z "$mono" || ! -f "$mono" || ! "$mono" -nt "$out/babeldoc.log" ]]; then
      measure_pdf="$out/translated-left.pdf"
      "$PY" - <<PY
import pymupdf
src = pymupdf.open(r"""$dual""")
pg = src[0]
w = pg.rect.width / 2
out = pymupdf.open()
p = out.new_page(width=w, height=pg.rect.height)
p.show_pdf_page(p.rect, src, 0, clip=pymupdf.Rect(0, 0, w, pg.rect.height))
out.save(r"""$measure_pdf""")
out.close(); src.close()
print("derived", r"""$measure_pdf""")
PY
      mono="$measure_pdf"
    fi
  fi

  local ocr_m="" transl_m="{}"
  ocr_m="$(measure_pdf_fonts "$WORK/page1.hpd-ocr.pdf")"
  if [[ -n "$mono" && -f "$mono" ]]; then
    transl_m="$(measure_pdf_fonts "$mono")"
    render_png "$mono" "$WORK/page1.$v.mono.png"
  fi
  if [[ -n "$dual" && -f "$dual" ]]; then
    render_png "$dual" "$WORK/page1.$v.dual.png"
  fi
  local fallback
  fallback="$(grep -c 'try fallback' "$out/babeldoc.log" || true)"

  "$PY" - <<PY
import json, pathlib, datetime
path = pathlib.Path(r"""$BASELINE""")
data = {}
if path.is_file():
    data = json.loads(path.read_text())
data.setdefault("generated_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
data["work_dir"] = r"""$WORK"""
data["source"] = r"""$SRC"""
data["model"] = r"""$MODEL"""
data.setdefault("variants", {})
data["variants"][r"""$v"""] = {
    "flags": r"""$flags""",
    "elapsed_s": $elapsed,
    "fallback_count": int("""$fallback""" or 0),
    "ocr_layer": json.loads(r"""$ocr_m"""),
    "mono": json.loads(r"""$transl_m""") if r"""$transl_m""" else None,
    "mono_pdf": r"""$mono""" or None,
    "dual_pdf": r"""$dual""" or None,
    "mono_png": r"""$WORK/page1.$v.mono.png""" if pathlib.Path(r"""$WORK/page1.$v.mono.png""").is_file() else None,
    "dual_png": r"""$WORK/page1.$v.dual.png""" if pathlib.Path(r"""$WORK/page1.$v.dual.png""").is_file() else None,
}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print("updated", path)
print(json.dumps(data["variants"][r"""$v"""], ensure_ascii=False, indent=2))
PY
}

extract_page1

case "$VARIANT" in
  all)
    run_hpd 0
    for v in V0 V1 V2; do run_variant "$v"; done
    echo "NOTE: V3/V4 require 007b/007d; run after those land: bash scripts/bench-scanned-page1.sh V3"
    ;;
  V3|V4|V5)
    run_hpd 1
    if [[ "$VARIANT" == "V5" ]]; then
      export PDF2ZH_LLM_BATCH_PARAS="${PDF2ZH_LLM_BATCH_PARAS:-3}"
      export PDF2ZH_LLM_BATCH_TOKENS="${PDF2ZH_LLM_BATCH_TOKENS:-120}"
    fi
    run_variant "$VARIANT"
    ;;
  V0|V1|V2)
    run_hpd 0
    run_variant "$VARIANT"
    ;;
  *)
    echo "usage: $0 [V0|V1|V2|V3|V4|V5|all]" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-033n：对当前 HEAD 重跑 11 页样本 BabelDOC → imgtr → tbltr。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
PDF2ZH="${QYUNSLATION_PDF2ZH_CLI:-pdf2zh_next}"
HEAD="$(git -C "$ROOT" rev-parse --short HEAD)"
STAGING="/tmp/plan033m-${HEAD}"
SAMPLE="${QYUNSLATION_PLAN033_SAMPLE:-}"
MODEL="${QYUNSLATION_OLLAMA_MODEL:-qwen3.6:35b-a3b}"
OLLAMA_HOST="${QYUNSLATION_OLLAMA_HOST:-http://100.67.66.123:11434}"
STEM="1-s2.0-S2666636725013958-main.no_watermark.zh"

if [[ -z "$SAMPLE" ]]; then
  for cand in \
    "/home/dev/.hermes/attachments/1-s2.0-S2666636725013958-main.pdf" \
    /home/dev/pdf2zh/pdf2zh_files/*/1-s2.0-S2666636725013958-main.pdf
  do
    if [[ -f "$cand" ]]; then
      SAMPLE="$cand"
      break
    fi
  done
fi

if [[ ! -f "$SAMPLE" ]]; then
  echo "BLOCKED: QYUNSLATION_PLAN033_SAMPLE missing" >&2
  exit 2
fi

if [[ ! -x "$PY" ]]; then
  echo "FAIL: venv python missing at $PY" >&2
  exit 1
fi

mkdir -p "$STAGING"
printf '%s\n' "$HEAD" >"$STAGING/HEAD"
export QYUNSLATION_PLAN033_SAMPLE="$SAMPLE"

CONFIG_SRC="${QYUNSLATION_PDF2ZH_CONFIG:-/home/dev/pdf2zh/config.toml}"
CONFIG="$STAGING/config.toml"
python3 - <<PY
from pathlib import Path
src = Path("$CONFIG_SRC")
text = src.read_text(encoding="utf-8") if src.is_file() else ""
out = []
for line in text.splitlines():
    s = line.strip()
    if s == "gui = true":
        out.append("gui = false")
    elif line.startswith("output = "):
        out.append('output = "$STAGING"')
    elif s == "ignore_cache = false":
        out.append("ignore_cache = true")
    else:
        out.append(line)
if not any("gui = false" in x for x in out):
    out.append("gui = false")
Path("$CONFIG").write_text("\\n".join(out) + "\\n", encoding="utf-8")
print("config", "$CONFIG")
PY

LOG="$STAGING/run.log"
printf 'head=%s sample=%s start=%s\n' "$HEAD" "$SAMPLE" "$(date -Is)" >"$LOG"

export PYTHONPATH="$ROOT"
export PATH="${HOME}/.local/bin:/usr/bin:/bin:${PATH:-}"

"$PDF2ZH" \
  --config-file "$CONFIG" \
  --disable-config-auto-save \
  --ollama \
  --ollama-model "$MODEL" \
  --ollama-host "$OLLAMA_HOST" \
  --lang-in en \
  --lang-out zh \
  --output "$STAGING" \
  --ignore-cache \
  --no-auto-extract-glossary \
  --watermark-output-mode no_watermark \
  "$SAMPLE" >>"$LOG" 2>&1
babel_exit=$?
printf 'babeldoc_exit=%s end=%s\n' "$babel_exit" "$(date -Is)" >>"$LOG"
if [[ "$babel_exit" -ne 0 ]]; then
  echo "FAIL: BabelDOC exit $babel_exit (see $LOG)" >&2
  exit 1
fi

MONO="$STAGING/${STEM}.mono.pdf"
DUAL="$STAGING/${STEM}.dual.pdf"
for f in "$MONO" "$DUAL"; do
  if [[ ! -f "$f" ]]; then
    echo "FAIL: missing $f" >&2
    exit 1
  fi
done

POST_LOG="$STAGING/post.log"
if [[ -f /home/dev/pdf2zh/office.env ]]; then
  eval "$(python3 - <<'ENVPY'
import shlex
from pathlib import Path
for line in Path('/home/dev/pdf2zh/office.env').read_text(encoding='utf-8').splitlines():
    s = line.strip()
    if not s or s.startswith('#') or '=' not in s:
        continue
    k, v = s.split('=', 1)
    print(f'export {k.strip()}={shlex.quote(v.strip())}')
ENVPY
)"
fi
export QYUNSLATION_TABLE_TRANSLATE_CACHE="$STAGING/table-zh-cache.json"

"$PY" - <<PY >>"$POST_LOG" 2>&1
import sys
from pathlib import Path

ROOT = Path("$ROOT")
SCRIPTS = ROOT / "scripts"
for p in (str(SCRIPTS), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pdf_image_translate import translate_pdf_images
from pdf_table_translate import translate_pdf_tables
from qyunslation.structure.model_trace import bind_task_model_trace
from qyunslation.structure.scan_pdf import PdfStructureScanner

sample = Path("$SAMPLE")
mono = Path("$MONO")
dual = Path("$DUAL")
bind_task_model_trace(
    model_id="$MODEL",
    endpoint="${OLLAMA_HOST%/}/v1",
)
manifest = PdfStructureScanner().scan(sample)
mono_out = translate_pdf_images(mono, to_lang="简体中文", structure_manifest=manifest)
mono_out = translate_pdf_tables(
    mono_out, origin=sample, to_lang="简体中文", structure_manifest=manifest
)
dual_out = translate_pdf_images(dual, to_lang="简体中文", x_min_frac=0.5)
dual_out = translate_pdf_tables(
    dual_out,
    origin=sample,
    to_lang="简体中文",
    structure_manifest=manifest,
    x_min_frac=0.5,
)
print("mono", mono_out)
print("dual", dual_out)
PY
post_exit=$?
printf 'post_exit=%s end=%s\n' "$post_exit" "$(date -Is)" >>"$POST_LOG"
if [[ "$post_exit" -ne 0 ]]; then
  echo "FAIL: post-process exit $post_exit (see $POST_LOG)" >&2
  exit 1
fi

"$PY" - <<PY >"$STAGING/033n-inspect.json"
import json
from qyunslation.structure.plan033_final import inspect_final, patch_signature
report = inspect_final()
report["patch_signature"] = patch_signature()
print(json.dumps(report, ensure_ascii=False, indent=2))
PY

echo "OK: staging=$STAGING"
exit 0

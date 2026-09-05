# SPDX-License-Identifier: MPL-2.0
"""书信/扫描件全文翻译系统提示（跨页上下文）。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

PROMPT = (
    "/no_think You are a professional, authentic machine translation engine "
    "for multi-page FDA/regulatory letters. Keep terminology consistent across "
    "the whole document. A paragraph at the top or bottom of a page may continue "
    "across the page break: translate it as body text, never as a caption, "
    "heading, or footnote. Do not drop or shrink trailing sentences that look "
    "incomplete."
)
OLLAMA_HOST = os.environ.get("QYUNSLATION_OLLAMA_HOST", "http://100.67.66.123:11434")
OLLAMA_MODEL = os.environ.get("QYUNSLATION_BENCH_MODEL", "qwen3.6:35b-a3b")


def system_prompt(*, extra_context: str | None = None) -> str:
    ctx = extra_context or os.environ.get("QYUNSLATION_TRANSLATE_CONTEXT", "").strip()
    if not ctx:
        path = os.environ.get("QYUNSLATION_TRANSLATE_CONTEXT_FILE", "").strip()
        if path and Path(path).is_file():
            ctx = Path(path).read_text(encoding="utf-8").strip()
    if not ctx:
        return PROMPT
    return f"{PROMPT}\n\nAdjacent-page context (do not translate this block, only use it):\n{ctx[:2000]}"


def translate_blocks(
    blocks: list[str],
    *,
    extra_context: str = "",
    glossary: list[tuple[str, str]] | None = None,
    host: str | None = None,
    model: str | None = None,
) -> list[str]:
    """用 qwen3.6:35b-a3b 按块译中文。失败则原样返回该块。"""
    if not blocks:
        return []
    gloss = ""
    if glossary:
        gloss = "\n".join(f"{s} => {t}" for s, t in glossary[:80])
    numbered = "\n\n".join(f"[{i}]\n{b}" for i, b in enumerate(blocks, 1))
    user = (
        "Translate each numbered English block into Simplified Chinese. "
        "Return a JSON array of strings only, same length and order. "
        "Do not summarize, skip, or merge away any clause, list item, or trailing "
        "half-sentence. Keep FDA/GS301/Vabysmo/faricimab/CMC/CAA/PTM/IND/PIND/PHS Act "
        "as specified by the glossary. Do not add headings or commentary.\n"
    )
    if gloss:
        user += f"\nGlossary:\n{gloss}\n"
    user += f"\n{numbered}"
    payload = {
        "model": model or OLLAMA_MODEL,
        "system": system_prompt(extra_context=extra_context),
        "prompt": user,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2, "num_predict": 4096},
    }
    url = (host or OLLAMA_HOST).rstrip("/") + "/api/generate"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ollama translate failed: {exc}") from exc
    raw = (data.get("response") or "").strip()
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end <= start:
        return list(blocks)
    try:
        arr = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return list(blocks)
    if not isinstance(arr, list) or len(arr) != len(blocks):
        return list(blocks)
    out: list[str] = []
    for src, zh in zip(blocks, arr):
        t = " ".join(str(zh or "").split()).strip()
        out.append(t or src)
    return out

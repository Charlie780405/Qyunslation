#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-042b：BabelDOC 译前精确直替短标签 / 登记表固定字段。

命中 glossaries/regulatory-form-fields.csv（及 merged 中 form/org 层）的段落
直接写入译文并跳过 LLM，绕过 min_text_length=5 导致的短值格漏译。
"""
from __future__ import annotations

import sys
from pathlib import Path

SITE = Path.home() / ".local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
IL = SITE / "babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
MARKER = "_qy_042b_short_label_direct"


def _helper_block() -> str:
    return f'''
# PLAN-042b short-label direct replace (apply-pdf2zh-042b-short-label.py)
{MARKER}_MAP = None


def {MARKER}_load():
    global {MARKER}_MAP
    if {MARKER}_MAP is not None:
        return {MARKER}_MAP
    mapping = {{}}
    try:
        from qyunslation.glossary.governance import (
            GLOSSARIES_DIR,
            load_glossary_csv,
            merge_by_priority,
        )
        entries = []
        for name, layer in (
            ("org-proper-nouns.csv", "org"),
            ("regulatory-form-fields.csv", "form"),
        ):
            path = GLOSSARIES_DIR / name
            entries.extend(
                load_glossary_csv(path, default_layer=layer, curated_only=True, skip_junk=True)
            )
        mapping = merge_by_priority(entries)
    except Exception:
        mapping = {{}}
    {MARKER}_MAP = mapping
    return mapping


def {MARKER}_lookup(text: str):
    raw = (text or "").strip()
    if not raw:
        return None
    table = {MARKER}_load()
    if raw in table:
        return table[raw]
    key = " ".join(raw.split()).casefold()
    for src, tgt in table.items():
        if " ".join(src.split()).casefold() == key:
            return tgt
    return None

'''


def patch_il(text: str) -> tuple[str, bool]:
    changed = False
    if MARKER not in text:
        anchor = "logger = logging.getLogger(__name__)"
        if anchor not in text:
            print("ERROR: il_translator logger anchor not found", file=sys.stderr)
            return text, False
        text = text.replace(anchor, anchor + _helper_block(), 1)
        changed = True

    # Inject before min_text_length skip in process_page loop
    inject = f"""            _qy_direct = {MARKER}_lookup(paragraph.unicode)
            if _qy_direct is not None:
                try:
                    self.set_paragraph_translated(paragraph, _qy_direct)
                except Exception:
                    try:
                        paragraph.unicode = _qy_direct
                    except Exception:
                        pass
                if pbar:
                    pbar.advance(1)
                translated_ids.add(id(paragraph))
                continue

"""
    # Prefer placement just before min_text_length check
    min_anchor = "            if len(paragraph.unicode) < self.translation_config.min_text_length:"
    if inject.strip() not in text and min_anchor in text:
        # Only first occurrence inside process_page ideally — replace first
        text = text.replace(min_anchor, inject + min_anchor, 1)
        changed = True
    return text, changed


def main() -> int:
    if not IL.is_file():
        print(f"ERROR: missing {IL}", file=sys.stderr)
        return 1
    original = IL.read_text(encoding="utf-8")
    patched, changed = patch_il(original)
    if changed:
        IL.write_text(patched, encoding="utf-8")
        print(f"patched {IL}")
    else:
        print(f"already patched or no change: {IL}")
    # sanity
    if MARKER not in patched:
        print("ERROR: marker missing after patch", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-042b / PLAN-043a：BabelDOC 译前精确直替短标签 / 登记表固定字段。

命中 glossaries/regulatory-form-fields.csv（及 merged 中 form/org 层）的段落
经 post_translate_paragraph 写回 composition，绕过 min_text_length=5 导致的短值格漏译。
写回失败时不标记已译，回退 LLM。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SITE = Path.home() / ".local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
IL = SITE / "babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
MARKER = "_qy_042b_short_label_direct"
OLD_INJECT_RE = re.compile(
    r"            _qy_direct = _qy_042b_short_label_direct_lookup\(paragraph\.unicode\)\n"
    r"            if _qy_direct is not None:\n"
    r"(?:.*?\n)*?"
    r"                continue\n\n",
    re.MULTILINE,
)
OLD_LOOKUP_RE = re.compile(
    r"def _qy_042b_short_label_direct_lookup\(text: str\):\n"
    r"(?:    .*\n)*?"
    r"    return None\n",
    re.MULTILINE,
)
OLD_INJECT_NO_PENDING_RE = re.compile(
    r"            _qy_suffix = None\n"
    r"(?:            .*\n)*?"
    r"                    continue\n\n"
    r"(?=            if len\(paragraph\.unicode\) < self\.translation_config\.min_text_length:)",
    re.MULTILINE,
)


def _helper_block() -> str:
    return f'''
# PLAN-042b/043a short-label direct replace (apply-pdf2zh-042b-short-label.py)
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
            normalize_source,
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


def {MARKER}_lookup_key(text: str):
    raw = (text or "").strip()
    if not raw:
        return None
    table = {MARKER}_load()
    if raw in table:
        return table[raw]
    try:
        from qyunslation.glossary.governance import normalize_source
        key = normalize_source(raw)
    except Exception:
        key = " ".join(raw.split()).casefold()
    for src, tgt in table.items():
        try:
            from qyunslation.glossary.governance import normalize_source as _ns
            if _ns(src) == key:
                return tgt
        except Exception:
            if " ".join(src.split()).casefold() == key:
                return tgt
    return None


def {MARKER}_lookup(text: str, suffix: str | None = None):
    hit = {MARKER}_lookup_key(text)
    if hit is not None:
        return hit
    suf = (suffix or "").strip()
    if suf and len(suf) <= 2:
        joined = (text or "").strip() + suf
        return {MARKER}_lookup_key(joined)
    return None

'''


def _inject_block() -> str:
    return f"""            _qy_suffix = None
            if _qy_para_idx + 1 < len(_qy_para_list):
                _qy_nxt = _qy_para_list[_qy_para_idx + 1]
                _qy_nxt_u = getattr(_qy_nxt, "unicode", None) or ""
                if 0 < len(_qy_nxt_u.strip()) <= 2:
                    _qy_suffix = _qy_nxt_u.strip()
            _qy_direct = {MARKER}_lookup(paragraph.unicode, _qy_suffix)
            _qy_direct_pending = False
            if _qy_direct is not None:
                _qy_applied = False
                if tracker is not None:
                    try:
                        _qy_xmap = page_xobj_font_map.get(paragraph.xobj_id, page_font_map)
                        _qy_tr = tracker.new_paragraph()
                        _qy_inp = self.il_translator.get_translate_input(
                            paragraph, page_font_map, disable_rich_text_translate=True
                        )
                        if _qy_inp is not None:
                            _qy_tr.set_pdf_unicode(paragraph.unicode)
                            _qy_tr.set_input(_qy_inp.unicode)
                            _qy_applied = self.il_translator.post_translate_paragraph(
                                paragraph, _qy_tr, _qy_inp, _qy_direct
                            )
                    except Exception:
                        _qy_applied = False
                if _qy_applied:
                    if pbar:
                        pbar.advance(1)
                    translated_ids.add(id(paragraph))
                    if _qy_suffix and _qy_para_idx + 1 < len(_qy_para_list):
                        _qy_nxt2 = _qy_para_list[_qy_para_idx + 1]
                        if (getattr(_qy_nxt2, "unicode", None) or "").strip() == _qy_suffix:
                            translated_ids.add(id(_qy_nxt2))
                    continue
                _qy_direct_pending = True

"""


def patch_il(text: str) -> tuple[str, bool]:
    changed = False
    if MARKER not in text:
        anchor = "logger = logging.getLogger(__name__)"
        if anchor not in text:
            print("ERROR: il_translator logger anchor not found", file=sys.stderr)
            return text, False
        text = text.replace(anchor, anchor + _helper_block(), 1)
        changed = True
    if f"{MARKER}_lookup_key" not in text:
        new_lookup = (
            f"def {MARKER}_lookup_key(text: str):\n"
            f"    raw = (text or \"\").strip()\n"
            f"    if not raw:\n"
            f"        return None\n"
            f"    table = {MARKER}_load()\n"
            f"    if raw in table:\n"
            f"        return table[raw]\n"
            f"    try:\n"
            f"        from qyunslation.glossary.governance import normalize_source\n"
            f"        key = normalize_source(raw)\n"
            f"    except Exception:\n"
            f"        key = \" \".join(raw.split()).casefold()\n"
            f"    for src, tgt in table.items():\n"
            f"        try:\n"
            f"            from qyunslation.glossary.governance import normalize_source as _ns\n"
            f"            if _ns(src) == key:\n"
            f"                return tgt\n"
            f"        except Exception:\n"
            f"            if \" \".join(src.split()).casefold() == key:\n"
            f"                return tgt\n"
            f"    return None\n\n\n"
            f"def {MARKER}_lookup(text: str, suffix: str | None = None):\n"
            f"    hit = {MARKER}_lookup_key(text)\n"
            f"    if hit is not None:\n"
            f"        return hit\n"
            f"    suf = (suffix or \"\").strip()\n"
            f"    if suf and len(suf) <= 2:\n"
            f"        joined = (text or \"\").strip() + suf\n"
            f"        return {MARKER}_lookup_key(joined)\n"
            f"    return None\n"
        )
        if OLD_LOOKUP_RE.search(text):
            text = OLD_LOOKUP_RE.sub(new_lookup, text, count=1)
            changed = True

    # Remove broken 042b inject (043a idempotent upgrade)
    if OLD_INJECT_RE.search(text):
        text = OLD_INJECT_RE.sub("", text, count=1)
        changed = True
    elif "self.set_paragraph_translated(paragraph, _qy_direct)" in text:
        # fallback strip
        start = text.find("            _qy_direct = _qy_042b_short_label_direct_lookup")
        if start >= 0:
            end = text.find("                continue\n", start)
            if end >= 0:
                text = text[:start] + text[end + len("                continue\n\n") :]
                changed = True

    inject = _inject_block()
    min_anchor = "            if len(paragraph.unicode) < self.translation_config.min_text_length:"
    min_anchor_pending = (
        "            if (\n"
        "                not _qy_direct_pending\n"
        "                and len(paragraph.unicode) < self.translation_config.min_text_length\n"
        "            ):"
    )

    if "_qy_direct_pending" not in text and OLD_INJECT_NO_PENDING_RE.search(text):
        text = OLD_INJECT_NO_PENDING_RE.sub(inject, text, count=1)
        changed = True
    if min_anchor_pending not in text and min_anchor in text and "_qy_direct_pending" in text:
        text = text.replace(min_anchor, min_anchor_pending, 1)
        changed = True

    # Undo mistaken enumerate in find_title_paragraph (must stay plain loop)
    broken_title = (
        "        for page in docs.page:\n"
        "            _qy_para_list = list(page.pdf_paragraph)\n"
        "        for _qy_para_idx, paragraph in enumerate(_qy_para_list):"
    )
    fixed_title = (
        "        for page in docs.page:\n"
        "            for paragraph in page.pdf_paragraph:"
    )
    if broken_title in text:
        text = text.replace(broken_title, fixed_title, 1)
        changed = True

    # Enumerate only in process_page (suffix join needs para index)
    enum_anchor = (
        "        total_token_count = 0\n"
        "        for paragraph in page.pdf_paragraph:"
    )
    enum_replacement = (
        "        total_token_count = 0\n"
        "        _qy_para_list = list(page.pdf_paragraph)\n"
        "        for _qy_para_idx, paragraph in enumerate(_qy_para_list):"
    )
    if enum_replacement not in text and enum_anchor in text:
        text = text.replace(enum_anchor, enum_replacement, 1)
        changed = True

    if inject.strip() not in text and min_anchor in text:
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
    if MARKER not in patched:
        print("ERROR: marker missing after patch", file=sys.stderr)
        return 1
    if "post_translate_paragraph" not in patched:
        print("ERROR: 043a writeback not present after patch", file=sys.stderr)
        return 1
    if "set_paragraph_translated" in patched:
        print("ERROR: old broken inject still present", file=sys.stderr)
        return 1
    if f"{MARKER}_lookup_key" not in patched:
        print("ERROR: suffix lookup helper missing after patch", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

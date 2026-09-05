#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-008d：幂等打 gui.py 文档类型下拉 + 翻译前应用模板。不改泰州 HPD。"""
from __future__ import annotations

import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
)

MARKER = "doc_profile_dropdown"
DROP_ANCHOR = """                        primary_font_family = gr.Dropdown(
                            label=_("Primary font family for translated text"),
                            choices=["Auto", "serif", "sans-serif", "script"],
                            value="Auto"
                            if not settings.translation.primary_font_family
                            else settings.translation.primary_font_family,
                            interactive=True,
                        )
"""

DROP_NEW = DROP_ANCHOR + """
                        doc_profile_dropdown = gr.Dropdown(
                            label="文档类型模板",
                            choices=["自动", "正式书信", "学术文献", "IND递交资料", "通用"],
                            value="自动",
                            interactive=True,
                        )
"""

UPLOAD_ANCHOR = """        file_input.upload(
            on_file_upload,
            inputs=[file_input, state],
            outputs=[result_file_selector, state, uploaded_files_view],
        )
"""

UPLOAD_NEW = UPLOAD_ANCHOR + """
        def _qy_hint_doc_profile(files, choice, st):
            import sys as _sys
            from pathlib import Path as _P
            _sys.path.insert(0, "/home/dev/qyunslation/scripts")
            from doc_profile import hint_choice, detect, AUTO_CHOICE
            st = st or {}
            if choice and not str(choice).startswith(AUTO_CHOICE):
                st["_doc_profile_ui"] = choice
                return gr.update(), st
            path = None
            if files:
                f0 = files[0]
                path = _P(f0.name if hasattr(f0, "name") else f0)
            detected = detect(path) if path and path.is_file() else "generic"
            st["_doc_profile_ui"] = AUTO_CHOICE
            st["_doc_profile_detected"] = detected
            return gr.update(value=hint_choice(detected)), st

        file_input.upload(
            _qy_hint_doc_profile,
            inputs=[file_input, doc_profile_dropdown, state],
            outputs=[doc_profile_dropdown, state],
        )
"""

APPLY_ANCHOR = """        if not state.get("_hpd_retried"):
            import sys as _sys

            _sys.path.insert(0, "/home/dev/pdf2zh")
            from hpd_ocr import ocr_pdf_with_hpd, pdf_needs_hpd
"""

APPLY_NEW = """        import sys as _qy_sys
        from pathlib import Path as _qy_P
        _qy_sys.path.insert(0, "/home/dev/qyunslation/scripts")
        from doc_profile import apply as _qy_apply, patch_line_skip as _qy_patch_ls, patch_letter_typesetting as _qy_patch_letter, resolve as _qy_resolve
        _qy_choice = (state or {}).get("_doc_profile_ui") or "自动"
        _qy_name = _qy_resolve(_qy_choice, _qy_P(file_path))
        _qy_prof = _qy_apply(_qy_name, settings)
        _qy_patch_ls(float(_qy_prof.get("line_skip") or 1.5))
        if _qy_name == "letter":
            _qy_patch_letter(_qy_prof)
        _qy_merge_agg = bool(_qy_prof.get("merge_aggressive", True))
        _qy_min_fs = float(_qy_prof.get("min_font_size") or 7.0)
        state["_doc_profile_applied"] = _qy_name
        try:
            from proper_nouns import harvest as _qy_harvest, glossary_args as _qy_gloss_args
            _qy_harvest(_qy_P(file_path))
            _qy_extra = []
            _qy_qx = _qy_P("/home/dev/pdf2zh/glossaries/qx027n.csv")
            if _qy_qx.is_file():
                _qy_extra.append(_qy_qx)
            _qy_g = _qy_gloss_args(_qy_extra)
            if _qy_g:
                _cur = getattr(getattr(settings, "translation", None), "glossaries", None) or ""
                settings.translation.glossaries = ",".join(
                    x for x in (_qy_g.split(",") + ([_cur] if _cur else [])) if x
                )
        except Exception as _qy_exc:
            import logging as _qy_log
            _qy_log.getLogger(__name__).warning("proper_nouns harvest 跳过: %s", _qy_exc)

        if not state.get("_hpd_retried"):
            import sys as _sys

            _sys.path.insert(0, "/home/dev/pdf2zh")
            from hpd_ocr import ocr_pdf_with_hpd, pdf_needs_hpd
"""

HPD_CALL_OLD = (
    "                file_path = ocr_pdf_with_hpd(Path(file_path), progress_cb=_hpd_progress)\n"
    "                settings.pdf.ocr_workaround = True\n"
    "                settings.pdf.skip_scanned_detection = True\n"
    "                settings.pdf.disable_rich_text_translate = True\n"
)
HPD_CALL_NEW = (
    "                import asyncio as _qy_aio_ocr\n"
    "                _qy_ocr_st = {\"f\": 0.04, \"d\": \"①识别\"}\n"
    "                def _hpd_progress(cur: int, total: int) -> None:\n"
    "                    _qy_ocr_st[\"f\"] = 0.04 + 0.36 * cur / max(total, 1)\n"
    "                    _qy_ocr_st[\"d\"] = f\"①识别 {cur}/{total} 页\"\n"
    "                _qy_ocr_task = _qy_aio_ocr.get_event_loop().run_in_executor(\n"
    "                    None,\n"
    "                    lambda: ocr_pdf_with_hpd(\n"
    "                        Path(file_path), progress_cb=_hpd_progress,\n"
    "                        aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n"
    "                        profile=_qy_name,\n"
    "                    ),\n"
    "                )\n"
    "                while not _qy_ocr_task.done():\n"
    "                    progress(_qy_ocr_st[\"f\"], desc=f\"{task_prefix}{_qy_ocr_st['d']}\")\n"
    "                    await _qy_aio_ocr.sleep(0.4)\n"
    "                file_path = await _qy_ocr_task\n"
    "                settings.pdf.ocr_workaround = True\n"
    "                settings.pdf.skip_scanned_detection = True\n"
    "                settings.pdf.disable_rich_text_translate = bool(\n"
    "                    _qy_prof.get(\"disable_rich_text_translate\", True)\n"
    "                )\n"
)

HPD_SYNC_BLOCK = (
    "                def _hpd_progress(cur: int, total: int) -> None:\n"
    "                    progress(0.04 + 0.36 * cur / max(total, 1), "
    "desc=f\"{task_prefix}①识别 {cur}/{total} 页\")\n"
    "\n"
    "                file_path = ocr_pdf_with_hpd(\n"
    "                    Path(file_path), progress_cb=_hpd_progress,\n"
    "                    aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n"
    "                    profile=_qy_name,\n"
    "                )\n"
)
HPD_ASYNC_BLOCK = (
    "                import asyncio as _qy_aio_ocr\n"
    "                _qy_ocr_st = {\"f\": 0.04, \"d\": \"①识别\"}\n"
    "                def _hpd_progress(cur: int, total: int) -> None:\n"
    "                    _qy_ocr_st[\"f\"] = 0.04 + 0.36 * cur / max(total, 1)\n"
    "                    _qy_ocr_st[\"d\"] = f\"①识别 {cur}/{total} 页\"\n"
    "                _qy_ocr_task = _qy_aio_ocr.get_event_loop().run_in_executor(\n"
    "                    None,\n"
    "                    lambda: ocr_pdf_with_hpd(\n"
    "                        Path(file_path), progress_cb=_hpd_progress,\n"
    "                        aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n"
    "                        profile=_qy_name,\n"
    "                    ),\n"
    "                )\n"
    "                while not _qy_ocr_task.done():\n"
    "                    progress(_qy_ocr_st[\"f\"], desc=f\"{task_prefix}{_qy_ocr_st['d']}\")\n"
    "                    await _qy_aio_ocr.sleep(0.4)\n"
    "                file_path = await _qy_ocr_task\n"
)

# 旧进度文案（无 async）
HPD_CALL_SYNC_LEGACY = (
    "                file_path = ocr_pdf_with_hpd(\n"
    "                    Path(file_path), progress_cb=_hpd_progress,\n"
    "                    aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n"
    "                    profile=_qy_name,\n"
    "                )\n"
)

RETRY_OLD = (
    "                ocr_path = ocr_pdf_with_hpd(Path(file_path))\n"
)
RETRY_NEW = (
    "                ocr_path = ocr_pdf_with_hpd(\n"
    "                    Path(file_path), aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n"
    "                    profile=_qy_name,\n"
    "                )\n"
)

RETRY_RICH_OLD = (
    "            settings.pdf.ocr_workaround = True\n"
    "            settings.pdf.skip_scanned_detection = True\n"
    "            settings.pdf.disable_rich_text_translate = True\n"
    "            return await _run_translation_task(\n"
)
RETRY_RICH_NEW = (
    "            settings.pdf.ocr_workaround = True\n"
    "            settings.pdf.skip_scanned_detection = True\n"
    "            settings.pdf.disable_rich_text_translate = bool(\n"
    "                _qy_prof.get(\"disable_rich_text_translate\", True)\n"
    "            )\n"
    "            return await _run_translation_task(\n"
)


APPLY_OLD_008 = """        import sys as _qy_sys
        from pathlib import Path as _qy_P
        _qy_sys.path.insert(0, "/home/dev/qyunslation/scripts")
        from doc_profile import apply as _qy_apply, patch_line_skip as _qy_patch_ls, resolve as _qy_resolve
        _qy_choice = (state or {}).get("_doc_profile_ui") or "自动"
        _qy_name = _qy_resolve(_qy_choice, _qy_P(file_path))
        _qy_prof = _qy_apply(_qy_name, settings)
        _qy_patch_ls(float(_qy_prof.get("line_skip") or 1.5))
        _qy_merge_agg = bool(_qy_prof.get("merge_aggressive", True))
        _qy_min_fs = float(_qy_prof.get("min_font_size") or 7.0)
        state["_doc_profile_applied"] = _qy_name

        if not state.get("_hpd_retried"):
            import sys as _sys

            _sys.path.insert(0, "/home/dev/pdf2zh")
            from hpd_ocr import ocr_pdf_with_hpd, pdf_needs_hpd
"""

HPD_CALL_008 = (
    "                file_path = ocr_pdf_with_hpd(\n"
    "                    Path(file_path), progress_cb=_hpd_progress,\n"
    "                    aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n"
    "                )\n"
)

RETRY_008 = (
    "                ocr_path = ocr_pdf_with_hpd(\n"
    "                    Path(file_path), aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n"
    "                )\n"
)




HARVEST_OLD = """        _qy_merge_agg = bool(_qy_prof.get("merge_aggressive", True))
        _qy_min_fs = float(_qy_prof.get("min_font_size") or 7.0)
        state["_doc_profile_applied"] = _qy_name

        if not state.get("_hpd_retried"):
"""
HARVEST_NEW = """        _qy_merge_agg = bool(_qy_prof.get("merge_aggressive", True))
        _qy_min_fs = float(_qy_prof.get("min_font_size") or 7.0)
        state["_doc_profile_applied"] = _qy_name
        try:
            from proper_nouns import harvest as _qy_harvest, glossary_args as _qy_gloss_args
            _qy_harvest(_qy_P(file_path))
            _qy_extra = []
            _qy_qx = _qy_P("/home/dev/pdf2zh/glossaries/qx027n.csv")
            if _qy_qx.is_file():
                _qy_extra.append(_qy_qx)
            _qy_g = _qy_gloss_args(_qy_extra)
            if _qy_g:
                _cur = getattr(getattr(settings, "translation", None), "glossaries", None) or ""
                settings.translation.glossaries = ",".join(
                    x for x in (_qy_g.split(",") + ([_cur] if _cur else [])) if x
                )
        except Exception as _qy_exc:
            import logging as _qy_log
            _qy_log.getLogger(__name__).warning("proper_nouns harvest 跳过: %s", _qy_exc)

        if not state.get("_hpd_retried"):
"""
LETTER_MARKER = "_qy_letter_reflow"
LETTER_ANCHOR = "        async for event in do_translate_async_stream(settings, file_path):\n"
LETTER_NEW = """        if _qy_name == "letter":
            _qy_dbg = _qy_P(str(file_path) + ".hpd-debug.json")
            if _qy_dbg.is_file():
                # _qy_letter_reflow
                import asyncio as _qy_aio
                from letter_pipeline import translate_scanned_letter as _qy_letter
                _qy_out = _qy_P(getattr(getattr(settings, "translation", None), "output", None) or ".")
                _qy_dest = _qy_out / f"{_qy_P(file_path).stem}.letter-mono.pdf"
                _qy_st = {"f": 0.40, "d": "②翻译"}
                def _qy_lp(frac, desc=""):
                    _qy_st["f"] = 0.40 + 0.58 * min(max(float(frac), 0.0), 1.0)
                    _qy_st["d"] = str(desc or "")
                _qy_task = _qy_aio.get_event_loop().run_in_executor(
                    None,
                    lambda: _qy_letter(_qy_P(file_path), _qy_dbg, _qy_dest, progress_cb=_qy_lp),
                )
                while not _qy_task.done():
                    progress(_qy_st["f"], desc=f"{task_prefix}{_qy_st['d']}")
                    await _qy_aio.sleep(0.4)
                await _qy_task
                progress(1.0, desc=f"{task_prefix}完成")
                return _qy_dest, _qy_dest, None, {}
        async for event in do_translate_async_stream(settings, file_path):
"""
LETTER_SYNC = """                # _qy_letter_reflow
                from letter_pipeline import translate_scanned_letter as _qy_letter
                _qy_out = _qy_P(getattr(getattr(settings, "translation", None), "output", None) or ".")
                _qy_dest = _qy_out / f"{_qy_P(file_path).stem}.letter-mono.pdf"
                def _qy_lp(frac, desc=""):
                    progress(0.40 + 0.58 * min(max(float(frac), 0.0), 1.0), desc=f"{task_prefix}{desc}")
                _qy_letter(_qy_P(file_path), _qy_dbg, _qy_dest, progress_cb=_qy_lp)
                return _qy_dest, _qy_dest, None, {}
"""
LETTER_ASYNC = """                # _qy_letter_reflow
                import asyncio as _qy_aio
                from letter_pipeline import translate_scanned_letter as _qy_letter
                _qy_out = _qy_P(getattr(getattr(settings, "translation", None), "output", None) or ".")
                _qy_dest = _qy_out / f"{_qy_P(file_path).stem}.letter-mono.pdf"
                _qy_st = {"f": 0.40, "d": "②翻译"}
                def _qy_lp(frac, desc=""):
                    _qy_st["f"] = 0.40 + 0.58 * min(max(float(frac), 0.0), 1.0)
                    _qy_st["d"] = str(desc or "")
                _qy_task = _qy_aio.get_event_loop().run_in_executor(
                    None,
                    lambda: _qy_letter(_qy_P(file_path), _qy_dbg, _qy_dest, progress_cb=_qy_lp),
                )
                while not _qy_task.done():
                    progress(_qy_st["f"], desc=f"{task_prefix}{_qy_st['d']}")
                    await _qy_aio.sleep(0.4)
                await _qy_task
                progress(1.0, desc=f"{task_prefix}完成")
                return _qy_dest, _qy_dest, None, {}
"""
BROKEN_INDENT = "                )\n                                settings.pdf.ocr_workaround"
FIXED_INDENT = "                )\n                settings.pdf.ocr_workaround"

REINSERT_MARKER = "_qy_graphic_reinsert"
REINSERT_ANCHOR = """            if _mono is None and _dual is not None:
                _mono = _dual  # _qy_mono_fallback_dual
            result_entry = {
"""
REINSERT_NEW = """            if _mono is None and _dual is not None:
                _mono = _dual  # _qy_mono_fallback_dual
            # _qy_graphic_reinsert
            try:
                import sys as _g_sys
                from pathlib import Path as _g_P
                _g_sys.path.insert(0, "/home/dev/qyunslation/scripts")
                from graphic_reinsert import reinsert as _qy_reinsert
                _mf = _g_P(str(file_path) + ".graphics.json")
                if _mf.is_file():
                    for _p in (_mono, _dual):
                        if _p:
                            _qy_reinsert(_g_P(_p), _mf)
            except Exception as _exc:
                import logging as _g_log
                _g_log.getLogger(__name__).warning("graphic reinsert 跳过: %s", _exc)
            result_entry = {
"""

def apply_fixed(text: str) -> str:
    changed = False
    if MARKER not in text:
        if DROP_ANCHOR not in text:
            print("ERROR: dropdown anchor not found", file=sys.stderr)
        else:
            text = text.replace(DROP_ANCHOR, DROP_NEW, 1)
            changed = True
    if "_qy_hint_doc_profile" not in text:
        if UPLOAD_ANCHOR not in text:
            print("ERROR: upload anchor not found", file=sys.stderr)
        else:
            text = text.replace(UPLOAD_ANCHOR, UPLOAD_NEW, 1)
            changed = True
    if "_qy_prof" not in text:
        if APPLY_ANCHOR not in text:
            print("ERROR: apply/HPD anchor not found", file=sys.stderr)
        else:
            text = text.replace(APPLY_ANCHOR, APPLY_NEW, 1)
            changed = True
    elif "_qy_patch_letter" not in text and APPLY_OLD_008 in text:
        text = text.replace(APPLY_OLD_008, APPLY_NEW, 1)
        changed = True
    if "aggressive=_qy_merge_agg" not in text:
        if HPD_CALL_OLD in text:
            text = text.replace(HPD_CALL_OLD, HPD_CALL_NEW, 1)
            changed = True
        else:
            print("WARNING: HPD call site not found", file=sys.stderr)
        if RETRY_OLD in text:
            text = text.replace(RETRY_OLD, RETRY_NEW, 1)
            changed = True
        if RETRY_RICH_OLD in text:
            text = text.replace(RETRY_RICH_OLD, RETRY_RICH_NEW, 1)
            changed = True
    if HPD_SYNC_BLOCK in text:
        text = text.replace(HPD_SYNC_BLOCK, HPD_ASYNC_BLOCK, 1)
        changed = True
    elif (
        "_qy_aio_ocr" not in text
        and HPD_CALL_SYNC_LEGACY in text
        and "def _hpd_progress" in text
    ):
        # 已有 sync progress + sync call：整块换成 async
        _prog_old = (
            "                def _hpd_progress(cur: int, total: int) -> None:\n"
            "                    progress(0.04 + 0.36 * cur / max(total, 1), "
            'desc=f"{task_prefix}①识别 {cur}/{total} 页")\n'
            "\n"
            + HPD_CALL_SYNC_LEGACY
        )
        if _prog_old in text:
            text = text.replace(_prog_old, HPD_ASYNC_BLOCK, 1)
            changed = True
        elif HPD_CALL_SYNC_LEGACY in text:
            text = text.replace(HPD_CALL_SYNC_LEGACY, HPD_ASYNC_BLOCK, 1)
            changed = True
    if "profile=_qy_name" not in text:
        if HPD_CALL_008 in text:
            text = text.replace(HPD_CALL_008, HPD_CALL_NEW.split("settings.pdf.ocr_workaround")[0], 1)
            # HPD_CALL_NEW includes ocr settings; only replace the call portion
            changed = True
        # 更稳妥：直接替换不含 profile 的调用块
        if (
            "aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n                )\n"
            in text
            and "profile=_qy_name" not in text
        ):
            text = text.replace(
                "aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n                )\n",
                "aggressive=_qy_merge_agg, min_font_size=_qy_min_fs,\n"
                "                    profile=_qy_name,\n"
                "                )\n",
            )
            changed = True
        if RETRY_008 in text:
            text = text.replace(RETRY_008, RETRY_NEW, 1)
            changed = True
    if "proper_nouns" not in text and HARVEST_OLD in text:
        text = text.replace(HARVEST_OLD, HARVEST_NEW, 1)
        changed = True
    if REINSERT_MARKER not in text:
        if REINSERT_ANCHOR in text:
            text = text.replace(REINSERT_ANCHOR, REINSERT_NEW, 1)
            changed = True
        else:
            print("WARNING: graphic reinsert anchor not found", file=sys.stderr)
    if BROKEN_INDENT in text:
        text = text.replace(BROKEN_INDENT, FIXED_INDENT)
        changed = True
    if LETTER_MARKER not in text:
        if LETTER_ANCHOR in text:
            text = text.replace(LETTER_ANCHOR, LETTER_NEW, 1)
            changed = True
        else:
            print("WARNING: letter reflow anchor not found", file=sys.stderr)
    if LETTER_SYNC in text:
        text = text.replace(LETTER_SYNC, LETTER_ASYNC, 1)
        changed = True
    _lp_old = (
        "                def _qy_lp(cur, total, msg=\"\"):\n"
        "                    progress(0.12 + 0.85 * cur / max(total, 1), "
        "desc=f\"{task_prefix}书信重绘 {cur}/{total} {msg}\")\n"
    )
    _lp_new = (
        "                def _qy_lp(frac, desc=\"\"):\n"
        "                    progress(0.40 + 0.58 * min(max(float(frac), 0.0), 1.0), "
        "desc=f\"{task_prefix}{desc}\")\n"
    )
    if _lp_old in text:
        text = text.replace(_lp_old, _lp_new, 1)
        changed = True
    _hpd_old = 'progress(0.02 + 0.08 * cur / max(total, 1), desc=f"HPD OCR {cur}/{total}")'
    _hpd_new = (
        'progress(0.04 + 0.36 * cur / max(total, 1), '
        'desc=f"{task_prefix}①识别 {cur}/{total} 页")'
    )
    if _hpd_old in text:
        text = text.replace(_hpd_old, _hpd_new)
        changed = True
    if "return str(_qy_dest), str(_qy_dest), None, {}" in text:
        text = text.replace(
            "return str(_qy_dest), str(_qy_dest), None, {}",
            "return _qy_dest, _qy_dest, None, {}",
            1,
        )
        changed = True
    if changed:
        print("patched:", GUI)
    else:
        print("already patched:", GUI)
    return text


def main() -> int:
    if not GUI.is_file():
        print(f"ERROR: {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    updated = apply_fixed(original)
    if updated != original:
        GUI.write_text(updated, encoding="utf-8")
    if MARKER not in updated or "_qy_prof" not in updated:
        print("ERROR: docprofile markers missing", file=sys.stderr)
        return 1
    if LETTER_MARKER not in updated:
        print("ERROR: letter reflow marker missing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

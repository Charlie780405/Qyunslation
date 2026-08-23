#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-005a：幂等打 pdf2zh gui.py HPD 扫描预 OCR 补丁。"""
from __future__ import annotations

import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
)

MARKER = "_hpd_retried"
ANCHOR = "    mono_path = None\n    dual_path = None\n    glossary_path = None\n    token_usage = None\n\n    try:\n        settings.basic.input_files = set()\n"

PRE_HPD = '''    mono_path = None
    dual_path = None
    glossary_path = None
    token_usage = None

    try:
        settings.basic.input_files = set()
        if not state.get("_hpd_retried"):
            import sys as _sys

            _sys.path.insert(0, "/home/dev/pdf2zh")
            from hpd_ocr import ocr_pdf_with_hpd, pdf_needs_hpd

            if pdf_needs_hpd(Path(file_path)):
                logger.warning("文字层过少，先走泰州 HPD OCR")

                def _hpd_progress(cur: int, total: int) -> None:
                    progress(0.02 + 0.08 * cur / max(total, 1), desc=f"HPD OCR {cur}/{total}")

                file_path = ocr_pdf_with_hpd(Path(file_path), progress_cb=_hpd_progress)
                settings.pdf.skip_scanned_detection = True
                state["_hpd_retried"] = True
'''

SCANNED_RETRY_OLD = '''    except gr.Error as e:
        logger.error(f"Gradio error: {e}")
        raise'''

SCANNED_RETRY_NEW = '''    except gr.Error as e:
        if "Scanned PDF" in str(e) and not state.get("_hpd_retried"):
            logger.warning("扫描件，改走泰州 HPD OCR 后重试")
            progress(0.05, desc="拍照/扫描 PDF：HPD OCR 识别中…")
            import sys as _sys

            _sys.path.insert(0, "/home/dev/pdf2zh")
            from hpd_ocr import ocr_pdf_with_hpd

            try:
                ocr_path = ocr_pdf_with_hpd(Path(file_path))
            except Exception as hpd_exc:
                raise gr.Error(f"HPD OCR failed: {hpd_exc}") from hpd_exc
            state["_hpd_retried"] = True
            settings.pdf.skip_scanned_detection = True
            return await _run_translation_task(
                settings, ocr_path, state, progress, task_prefix
            )
        logger.error(f"Gradio error: {e}")
        raise'''


def apply(text: str) -> str:
    if MARKER in text and "from hpd_ocr import ocr_pdf_with_hpd, pdf_needs_hpd" in text:
        # Ensure failure surfaces as gr.Error
        if "HPD OCR failed:" not in text and SCANNED_RETRY_OLD in text:
            # already has scanned branch from prior manual patch — upgrade error path if present
            old_ocr = "            ocr_path = ocr_pdf_with_hpd(Path(file_path))\n"
            new_ocr = (
                "            try:\n"
                "                ocr_path = ocr_pdf_with_hpd(Path(file_path))\n"
                "            except Exception as hpd_exc:\n"
                '                raise gr.Error(f"HPD OCR failed: {hpd_exc}") from hpd_exc\n'
            )
            if old_ocr in text and "HPD OCR failed:" not in text:
                text = text.replace(old_ocr, new_ocr, 1)
                print("patched: HPD failure → gr.Error")
            else:
                print("already patched:", GUI)
            return text
        print("already patched:", GUI)
        return text

    if ANCHOR not in text:
        print("ERROR: _run_translation_task anchor not found", file=sys.stderr)
        return text

    text = text.replace(ANCHOR, PRE_HPD + "        async for event in do_translate_async_stream", 1)
    # Fix accidental merge if we replaced too much — PRE_HPD already ends before async for
    # Actually ANCHOR doesn't include async for. Good.
    # Wait, I replaced ANCHOR with PRE_HPD + "        async for..." which would duplicate if next line is async for.
    # Let me fix: ANCHOR ends with input_files = set()\n so next line in file is already the async for or the if not state.
    
    return text


def apply_fixed(text: str) -> str:
    changed = False
    if "from hpd_ocr import ocr_pdf_with_hpd, pdf_needs_hpd" not in text:
        if ANCHOR not in text:
            print("ERROR: anchor not found", file=sys.stderr)
            return text
        text = text.replace(ANCHOR, PRE_HPD, 1)
        changed = True

    if "Scanned PDF" not in text.split("except gr.Error")[1][:800] if "except gr.Error" in text else True:
        # Find the except gr.Error in _run_translation_task
        if SCANNED_RETRY_OLD in text and "Scanned PDF" not in text:
            text = text.replace(SCANNED_RETRY_OLD, SCANNED_RETRY_NEW, 1)
            changed = True
        elif "Scanned PDF" in text and "HPD OCR failed:" not in text:
            old_ocr = "            ocr_path = ocr_pdf_with_hpd(Path(file_path))\n"
            new_ocr = (
                "            try:\n"
                "                ocr_path = ocr_pdf_with_hpd(Path(file_path))\n"
                "            except Exception as hpd_exc:\n"
                '                raise gr.Error(f"HPD OCR failed: {hpd_exc}") from hpd_exc\n'
            )
            if old_ocr in text:
                text = text.replace(old_ocr, new_ocr, 1)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

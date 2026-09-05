#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-005a/007c：幂等打 pdf2zh gui.py HPD 扫描预 OCR 补丁。

PLAN-007c：HPD 分支启用 ocr_workaround（反转 005a「禁止 ocr_workaround」）。
理由：扫描件不遮盖栅格英文则译文不可读；目标从「dual 可选中」升级为「一对一可读」。
仅在 HPD 分支设 ocr_workaround，不写进 config.toml 全局。
"""
from __future__ import annotations

import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
)

MARKER = "_hpd_retried"
OCR_MARKER = "settings.pdf.ocr_workaround = True"
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
                settings.pdf.ocr_workaround = True
                settings.pdf.skip_scanned_detection = True
                settings.pdf.disable_rich_text_translate = True
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
            settings.pdf.ocr_workaround = True
            settings.pdf.skip_scanned_detection = True
            settings.pdf.disable_rich_text_translate = True
            return await _run_translation_task(
                settings, ocr_path, state, progress, task_prefix
            )
        logger.error(f"Gradio error: {e}")
        raise'''

# 旧补丁：仅 skip_scanned_detection，无 ocr_workaround
_OLD_SKIP_ONLY = (
    "                file_path = ocr_pdf_with_hpd(Path(file_path), progress_cb=_hpd_progress)\n"
    "                settings.pdf.skip_scanned_detection = True\n"
    '                state["_hpd_retried"] = True\n'
)
_NEW_SKIP_OCR = (
    "                file_path = ocr_pdf_with_hpd(Path(file_path), progress_cb=_hpd_progress)\n"
    "                settings.pdf.ocr_workaround = True\n"
    "                settings.pdf.skip_scanned_detection = True\n"
    "                settings.pdf.disable_rich_text_translate = True\n"
    '                state["_hpd_retried"] = True\n'
)

_OLD_RETRY_SKIP = (
    '            state["_hpd_retried"] = True\n'
    "            settings.pdf.skip_scanned_detection = True\n"
    "            return await _run_translation_task(\n"
)
_NEW_RETRY_SKIP = (
    '            state["_hpd_retried"] = True\n'
    "            settings.pdf.ocr_workaround = True\n"
    "            settings.pdf.skip_scanned_detection = True\n"
    "            settings.pdf.disable_rich_text_translate = True\n"
    "            return await _run_translation_task(\n"
)


def apply_fixed(text: str) -> str:
    changed = False

    if "from hpd_ocr import ocr_pdf_with_hpd, pdf_needs_hpd" not in text:
        if ANCHOR not in text:
            print("ERROR: anchor not found", file=sys.stderr)
            return text
        text = text.replace(ANCHOR, PRE_HPD, 1)
        changed = True
    elif OCR_MARKER not in text and _OLD_SKIP_ONLY in text:
        text = text.replace(_OLD_SKIP_ONLY, _NEW_SKIP_OCR, 1)
        changed = True

    has_scanned = "Scanned PDF" in text and "except gr.Error" in text
    if not has_scanned:
        if SCANNED_RETRY_OLD in text:
            text = text.replace(SCANNED_RETRY_OLD, SCANNED_RETRY_NEW, 1)
            changed = True
        else:
            print("ERROR: Scanned PDF retry anchor not found", file=sys.stderr)
    else:
        if "HPD OCR failed:" not in text:
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
        if OCR_MARKER not in text.split("Scanned PDF", 1)[-1][:600] and _OLD_RETRY_SKIP in text:
            text = text.replace(_OLD_RETRY_SKIP, _NEW_RETRY_SKIP, 1)
            changed = True

    # 幂等：两处都必须含 ocr_workaround
    ocr_count = text.count(OCR_MARKER)
    if ocr_count < 2:
        print(f"WARNING: expected 2× {OCR_MARKER!r}, found {ocr_count}", file=sys.stderr)

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
    if OCR_MARKER not in updated:
        print("ERROR: ocr_workaround not applied", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

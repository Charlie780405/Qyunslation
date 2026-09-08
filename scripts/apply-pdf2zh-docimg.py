#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-027d / PLAN-033c：gui.py 注入 PDF 嵌图翻译。

033c：BabelDOC 只吃原稿；嵌图改在单语全文和双语右侧/交替译文页上做。
禁止再把 `.imgtr.pdf` 赋给 `file_path`。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
MARKER = "_qy_imgtr"
POST_MARKER = "_qy_imgtr_post"
SWAP_LINE = "file_path = _qy_new"

PRE_SNIPPET = '''
        # _qy_imgtr: PLAN-033c 原稿只读，嵌图改译文后处理
        if not state.get("_hpd_retried"):
            state["_pre_imgtr_origin_path"] = str(file_path)
'''

POST_SNIPPET = '''
            # _qy_imgtr_post
            try:
                import hashlib as _qy_hashlib
                import asyncio as _qy_aio_img
                import sys as _qy_sys
                from pathlib import Path as _qy_Pimg
                _qy_sys.path.insert(0, "/home/dev/pdf2zh")
                _qy_sys.path.insert(0, "/home/dev/qyunslation/scripts")
                from pdf_image_translate import translate_pdf_images as _qy_tr_pdf_img
                _qy_to = "简体中文"
                try:
                    if hasattr(settings, "translate") and getattr(
                        settings.translate, "lang_out", None
                    ):
                        _qy_to = settings.translate.lang_out
                except Exception:
                    pass
                _qy_manifest = None
                try:
                    _qy_origin = _qy_Pimg(
                        state.get("_pre_imgtr_origin_path") or file_path
                    )
                    from qyunslation.structure import ManifestStore as _QyStore
                    from qyunslation.structure.scan_pdf import (
                        PDF_STRUCTURE_SCANNER_NAME as _QyScanName,
                        PDF_STRUCTURE_SCANNER_VERSION as _QyScanVer,
                    )
                    _qy_full = _qy_hashlib.sha256(_qy_origin.read_bytes()).hexdigest()
                    _qy_manifest = _QyStore().get_current(
                        _qy_full,
                        producer_name=_QyScanName,
                        producer_version=_QyScanVer,
                    )
                except Exception:
                    _qy_manifest = None
                _qy_alt = bool(
                    getattr(
                        getattr(settings, "pdf", None),
                        "use_alternating_pages_dual",
                        False,
                    )
                )
                _qy_img_st = {"f": 0.92, "d": "译文插图翻译"}

                def _qy_img_progress(cur, total):
                    _qy_img_st["f"] = 0.92 + 0.07 * cur / max(total, 1)
                    _qy_img_st["d"] = f"译文插图翻译 ({cur}/{total})"

                def _qy_run_imgtr():
                    out_mono, out_dual = _mono, _dual
                    if _mono:
                        out_mono = str(
                            _qy_tr_pdf_img(
                                _qy_Pimg(_mono),
                                to_lang=str(_qy_to or "简体中文"),
                                progress_cb=_qy_img_progress,
                                structure_manifest=_qy_manifest,
                            )
                        )
                    if _dual and _dual != _mono:
                        out_dual = str(
                            _qy_tr_pdf_img(
                                _qy_Pimg(_dual),
                                to_lang=str(_qy_to or "简体中文"),
                                progress_cb=_qy_img_progress,
                                structure_manifest=None,
                                x_min_frac=None if _qy_alt else 0.5,
                                page_parity="even" if _qy_alt else None,
                            )
                        )
                    return out_mono, out_dual

                _qy_img_task = _qy_aio_img.get_event_loop().run_in_executor(
                    None, _qy_run_imgtr
                )
                while not _qy_img_task.done():
                    progress(_qy_img_st["f"], desc=f"{task_prefix}{_qy_img_st['d']}")
                    await _qy_aio_img.sleep(0.4)
                _mono, _dual = await _qy_img_task
            except Exception as _qy_img_exc:
                import logging as _qy_img_log
                _qy_img_log.getLogger(__name__).warning(
                    "译文插图翻译跳过: %s", _qy_img_exc
                )
'''

_PRE_BLOCK_RE = re.compile(
    r"\n[ \t]*# _qy_imgtr:.*?(?=\n[ \t]*(?:if _qy_name == \"letter\"|async for event in do_translate_async_stream))",
    re.S,
)


def _install_pre(text: str) -> tuple[str, bool]:
    if "_pre_imgtr_origin_path" in text and SWAP_LINE not in text:
        if "# _qy_imgtr:" in text:
            return text, False
    if _PRE_BLOCK_RE.search(text):
        updated, n = _PRE_BLOCK_RE.subn("\n" + PRE_SNIPPET.rstrip() + "\n", text, count=1)
        return updated, n > 0
    anchors = [
        "        async for event in do_translate_async_stream(settings, file_path):",
        "            async for event in do_translate_async_stream(settings, file_path):",
    ]
    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, PRE_SNIPPET + "\n" + anchor, 1), True
    return text, False


def _install_post(text: str) -> tuple[str, bool]:
    if POST_MARKER in text:
        return text, False
    reinsert = "            # _qy_graphic_reinsert\n"
    if reinsert in text:
        # 插在 graphic reinsert 整段之后、result_entry 之前
        marker = "            result_entry = {\n"
        idx = text.find(marker)
        if idx >= 0 and "# _qy_graphic_reinsert" in text[:idx]:
            return text[:idx] + POST_SNIPPET + "\n" + text[idx:], True
    fallback = "                _mono = _dual  # _qy_mono_fallback_dual\n"
    if fallback in text:
        return text.replace(fallback, fallback + POST_SNIPPET, 1), True
    return text, False


def apply(text: str) -> tuple[str, bool]:
    changed = False
    if SWAP_LINE in text or "# _qy_imgtr: PDF 内嵌插图翻译前置" in text:
        text, did = _install_pre(text)
        changed = changed or did
    elif MARKER not in text:
        text, did = _install_pre(text)
        changed = changed or did
    text, did = _install_post(text)
    changed = changed or did
    if POST_MARKER not in text:
        raise RuntimeError("找不到译文后处理锚点（graphic reinsert / mono fallback）")
    if SWAP_LINE in text:
        text = text.replace(
            "                    if _qy_new and _qy_Pimg(_qy_new).is_file():\n"
            "                        file_path = _qy_new\n",
            "",
        )
        changed = True
    return text, changed


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"FAIL: {msg}", file=sys.stderr)
            errs += 1

    need(MARKER in text, "marker missing")
    need("_pre_imgtr_origin_path" in text, "origin path missing")
    need(POST_MARKER in text, "imgtr post marker missing")
    need("translate_pdf_images" in text, "translate_pdf_images missing")
    need(SWAP_LINE not in text, "BabelDOC input still swapped to imgtr")
    need("x_min_frac" in text, "dual right-half filter missing")
    need(
        "do_translate_async_stream(settings, file_path)" in text,
        "stream call missing",
    )
    try:
        compile(text, str(GUI), "exec")
    except SyntaxError as e:
        print(f"FAIL: syntax {e}", file=sys.stderr)
        errs += 1
    return errs


def main() -> int:
    if not GUI.is_file():
        print(f"ERROR: missing {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    try:
        updated, changed = apply(original)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    if changed:
        GUI.write_text(updated, encoding="utf-8")
        print("patched:", GUI)
    else:
        print("already patched:", GUI)
    errs = verify(GUI.read_text(encoding="utf-8"))
    if errs:
        print(f"verify failed: {errs} error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

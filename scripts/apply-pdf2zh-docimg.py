#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-027d：gui.py 注入 PDF 内嵌图前置翻译（锚在 HPD 块后）。"""
from __future__ import annotations

import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
MARKER = "_qy_imgtr"

SNIPPET = r'''
        # _qy_imgtr: PDF 内嵌插图翻译前置（非扫描件）
        if not state.get("_hpd_retried"):
            import hashlib as _qy_hashlib
            from pathlib import Path as _qy_Pimg
            _qy_img_key = None
            try:
                _qy_raw = _qy_Pimg(str(file_path)).read_bytes()[: 1024 * 1024]
                _qy_img_key = _qy_hashlib.sha256(_qy_raw).hexdigest()
            except Exception:
                _qy_img_key = str(file_path)
            _qy_done = state.setdefault("_imgtr_done", {})
            if not _qy_done.get(_qy_img_key):
                try:
                    import sys as _qy_sys
                    _qy_sys.path.insert(0, "/home/dev/pdf2zh")
                    _qy_sys.path.insert(0, "/home/dev/qyunslation/scripts")
                    from pdf_image_translate import translate_pdf_images as _qy_tr_pdf_img
                    state["_pre_imgtr_origin_path"] = str(file_path)
                    def _qy_img_progress(cur, total):
                        try:
                            progress(0.08 + 0.12 * cur / max(total, 1), desc=f"文档插图翻译 ({cur}/{total})")
                        except Exception:
                            pass
                    _qy_lang = None
                    try:
                        _qy_lang = globals().get("lang_to")
                    except Exception:
                        _qy_lang = None
                    # settings / ui 侧语言
                    _qy_to = "简体中文"
                    try:
                        if hasattr(settings, "translate") and getattr(settings.translate, "lang_out", None):
                            _qy_to = settings.translate.lang_out
                    except Exception:
                        pass
                    _qy_new = _qy_tr_pdf_img(
                        _qy_Pimg(str(file_path)),
                        to_lang=str(_qy_to or "简体中文"),
                        progress_cb=_qy_img_progress,
                    )
                    if _qy_new and _qy_Pimg(_qy_new).is_file():
                        file_path = _qy_new
                    _qy_done[_qy_img_key] = True
                except Exception as _qy_img_exc:
                    logger.warning("PDF 插图翻译跳过: %s", _qy_img_exc)
'''


def apply(text: str) -> str:
    if MARKER in text and "_imgtr_done" in text:
        return text
    # Anchor: after HPD block sets state["_hpd_retried"] = True inside try of _run_translation_task
    # Prefer inserting right before "async for event in do_translate_async_stream"
    anchors = [
        "        async for event in do_translate_async_stream(settings, file_path):",
        "            async for event in do_translate_async_stream(settings, file_path):",
    ]
    placed = False
    for a in anchors:
        if a in text:
            text = text.replace(a, SNIPPET + "\n" + a, 1)
            placed = True
            break
    if not placed:
        # fallback after HPD marker
        hpd = 'state["_hpd_retried"] = True'
        idx = text.find(hpd)
        if idx < 0:
            raise RuntimeError("找不到 do_translate_async_stream / _hpd_retried 锚点")
        # find end of line after last _hpd_retried in pre-stream section — too fragile
        raise RuntimeError("找不到 do_translate_async_stream 锚点")
    return text


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"FAIL: {msg}", file=sys.stderr)
            errs += 1

    need(MARKER in text, "marker missing")
    need("translate_pdf_images" in text, "translate_pdf_images missing")
    need("_imgtr_done" in text, "_imgtr_done missing")
    need("_pre_imgtr_origin_path" in text, "origin path missing")
    try:
        compile(text, str(GUI), "exec")
    except SyntaxError as e:
        print(f"FAIL: syntax {e}", file=sys.stderr)
        errs += 1
    return errs


def main() -> int:
    original = GUI.read_text(encoding="utf-8")
    try:
        updated = apply(original)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    if updated != original:
        GUI.write_text(updated, encoding="utf-8")
        print("patched")
    else:
        print("already patched")
    return verify(GUI.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())

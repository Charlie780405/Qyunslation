#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-027d：gui.py 注入 PDF 内嵌图前置翻译（锚在 HPD 块后）。

PLAN-SSE：插图翻译改 run_in_executor，避免阻塞 asyncio 事件循环导致
Gradio /queue/data SSE 心跳停发、长任务前端误报连接中断。
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
EXEC_MARKER = "_qy_img_task = _qy_aio_img.get_event_loop().run_in_executor"
CANCEL_MARKER = "except _qy_aio_img.CancelledError"

SNIPPET = r'''
        # _qy_imgtr: PDF 内嵌插图翻译前置（非扫描件）
        if not state.get("_hpd_retried"):
            import hashlib as _qy_hashlib
            from pathlib import Path as _qy_Pimg
            import asyncio as _qy_aio_img
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
                    _qy_img_st = {"f": 0.08, "d": "文档插图翻译"}
                    def _qy_img_progress(cur, total):
                        _qy_img_st["f"] = 0.08 + 0.12 * cur / max(total, 1)
                        _qy_img_st["d"] = f"文档插图翻译 ({cur}/{total})"
                    _qy_to = "简体中文"
                    try:
                        if hasattr(settings, "translate") and getattr(settings.translate, "lang_out", None):
                            _qy_to = settings.translate.lang_out
                    except Exception:
                        pass
                    _qy_img_src = _qy_Pimg(str(file_path))
                    _qy_img_task = _qy_aio_img.get_event_loop().run_in_executor(
                        None,
                        lambda: _qy_tr_pdf_img(
                            _qy_img_src,
                            to_lang=str(_qy_to or "简体中文"),
                            progress_cb=_qy_img_progress,
                        ),
                    )
                    try:
                        while not _qy_img_task.done():
                            progress(_qy_img_st["f"], desc=f"{task_prefix}{_qy_img_st['d']}")
                            await _qy_aio_img.sleep(0.4)
                        _qy_new = await _qy_img_task
                    except _qy_aio_img.CancelledError:
                        _qy_img_task.cancel()
                        raise
                    if _qy_new and _qy_Pimg(_qy_new).is_file():
                        file_path = _qy_new
                    _qy_done[_qy_img_key] = True
                except Exception as _qy_img_exc:
                    logger.warning("PDF 插图翻译跳过: %s", _qy_img_exc)
'''

# 旧版同步块（无 run_in_executor）
OLD_BLOCK_RE = re.compile(
    r"\n[ \t]*# _qy_imgtr: PDF 内嵌插图翻译前置.*?"
    r"\n[ \t]*async for event in do_translate_async_stream\(settings, file_path\):",
    re.S,
)


def _insert_snippet(text: str) -> tuple[str, bool]:
    anchors = [
        "        async for event in do_translate_async_stream(settings, file_path):",
        "            async for event in do_translate_async_stream(settings, file_path):",
    ]
    for a in anchors:
        if a in text and MARKER not in text:
            return text.replace(a, SNIPPET + "\n" + a, 1), True
    return text, False


def apply(text: str) -> tuple[str, bool]:
    changed = False

    if MARKER in text and EXEC_MARKER in text and CANCEL_MARKER in text:
        return text, False

    if MARKER in text and EXEC_MARKER in text and CANCEL_MARKER not in text:
        old_wait = (
            "                    while not _qy_img_task.done():\n"
            "                        progress(_qy_img_st[\"f\"], desc=f\"{task_prefix}{_qy_img_st['d']}\")\n"
            "                        await _qy_aio_img.sleep(0.4)\n"
            "                    _qy_new = await _qy_img_task"
        )
        new_wait = (
            "                    try:\n"
            "                        while not _qy_img_task.done():\n"
            "                            progress(_qy_img_st[\"f\"], desc=f\"{task_prefix}{_qy_img_st['d']}\")\n"
            "                            await _qy_aio_img.sleep(0.4)\n"
            "                        _qy_new = await _qy_img_task\n"
            "                    except _qy_aio_img.CancelledError:\n"
            "                        _qy_img_task.cancel()\n"
            "                        raise"
        )
        if old_wait in text:
            return text.replace(old_wait, new_wait, 1), True
        print("WARNING: imgtr cancel upgrade anchor not found", file=sys.stderr)
        return text, False

    if MARKER in text and EXEC_MARKER not in text:
        m = OLD_BLOCK_RE.search(text)
        if not m:
            print("WARNING: imgtr block present but not replaceable", file=sys.stderr)
            return text, False
        anchor = m.group(0).split("\n")[-1]
        replacement = SNIPPET.rstrip() + "\n" + anchor
        text = text[: m.start()] + "\n" + replacement + text[m.end() :]
        return text, True

    text, inserted = _insert_snippet(text)
    if inserted:
        return text, True

    raise RuntimeError("找不到 do_translate_async_stream 锚点")


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"FAIL: {msg}", file=sys.stderr)
            errs += 1

    need(MARKER in text, "marker missing")
    need(EXEC_MARKER in text, "imgtr run_in_executor missing")
    need("await _qy_img_task" in text, "await imgtr task missing")
    need(CANCEL_MARKER in text, "imgtr CancelledError handler missing")
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

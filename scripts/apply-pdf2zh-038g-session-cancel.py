#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-038g：unload 取消按会话隔离，避免多用户互取消。须在 apply-pdf2zh-throughput.py 之后跑。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
MARKER = "PLAN-038g: per-session unload cancel"

NEW_BLOCK = '''_ACTIVE_TRANSLATION_TASK: asyncio.Task | None = None
_ACTIVE_TRANSLATION_TASKS: dict[str, asyncio.Task] = {}
_UNLOAD_CANCEL_HANDLES: dict[str, asyncio.TimerHandle] = {}
_UNLOAD_GRACE_SECONDS = 90


def _session_key(state: dict | None = None, request=None) -> str:
    if request is not None:
        hash_ = getattr(request, "session_hash", None)
        if hash_:
            return str(hash_)
    if state is not None:
        sid = state.get("session_id")
        if sid:
            return str(sid)
        return f"state:{id(state)}"
    return "global"


def _revoke_unload_cancel(session_key: str | None = None) -> None:
    if session_key is None:
        for key, handle in list(_UNLOAD_CANCEL_HANDLES.items()):
            if handle is not None and not handle.cancelled():
                handle.cancel()
            _UNLOAD_CANCEL_HANDLES.pop(key, None)
        return
    handle = _UNLOAD_CANCEL_HANDLES.pop(session_key, None)
    if handle is not None and not handle.cancelled():
        handle.cancel()


def _do_unload_cancel(session_key: str) -> None:
    _UNLOAD_CANCEL_HANDLES.pop(session_key, None)
    task = _ACTIVE_TRANSLATION_TASKS.pop(session_key, None)
    global _ACTIVE_TRANSLATION_TASK
    if _ACTIVE_TRANSLATION_TASK is task:
        _ACTIVE_TRANSLATION_TASK = None
    if task is not None and not task.done():
        logger.info(
            "Browser unload grace expired: cancelling session %s translation",
            session_key,
        )
        task.cancel()


def _cancel_active_translation_on_unload(request=None) -> None:
    """PLAN-038g: per-session unload cancel"""
    session_key = _session_key(request=request)
    _revoke_unload_cancel(session_key)
    task = _ACTIVE_TRANSLATION_TASKS.get(session_key)
    if task is None or task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            logger.warning("Browser unload: no event loop; cancelling immediately")
            _do_unload_cancel(session_key)
            return
    logger.info(
        "Browser unload: scheduling cancel for session %s in %ss",
        session_key,
        _UNLOAD_GRACE_SECONDS,
    )
    _UNLOAD_CANCEL_HANDLES[session_key] = loop.call_later(
        _UNLOAD_GRACE_SECONDS, _do_unload_cancel, session_key
    )


'''


def apply(text: str) -> str:
    if MARKER in text:
        return text

    # Replace single-slot grace block (PLAN-003c) through unload fn
    pat = re.compile(
        r"_ACTIVE_TRANSLATION_TASK: asyncio\.Task \| None = None\n"
        r".*?"
        r"def _cancel_active_translation_on_unload\(\) -> None:.*?"
        r"(?=async def stop_translate_file)",
        re.MULTILINE | re.DOTALL,
    )
    if not pat.search(text):
        raise SystemExit("038g: legacy unload block not found (run throughput patch first)")
    text = pat.sub(NEW_BLOCK, text, count=1)

    old_assign = (
        '            state["current_task"] = task\n'
        "            global _ACTIVE_TRANSLATION_TASK\n"
        "            _ACTIVE_TRANSLATION_TASK = task\n"
        "            _revoke_unload_cancel()"
    )
    new_assign = (
        '            state["current_task"] = task\n'
        "            global _ACTIVE_TRANSLATION_TASK\n"
        "            _ACTIVE_TRANSLATION_TASK = task\n"
        "            _sk = _session_key(state)\n"
        "            _ACTIVE_TRANSLATION_TASKS[_sk] = task\n"
        '            state["_unload_session_key"] = _sk\n'
        "            _revoke_unload_cancel(_sk)"
    )
    if old_assign not in text:
        raise SystemExit("038g: task assign anchor not found")
    text = text.replace(old_assign, new_assign, 1)

    old_finally = (
        '    finally:\n        state["current_task"] = None\n'
        "        global _ACTIVE_TRANSLATION_TASK\n"
        "        _ACTIVE_TRANSLATION_TASK = None\n"
        "        _revoke_unload_cancel()"
    )
    new_finally = (
        '    finally:\n        state["current_task"] = None\n'
        "        global _ACTIVE_TRANSLATION_TASK\n"
        "        _ACTIVE_TRANSLATION_TASK = None\n"
        '        _sk = state.pop("_unload_session_key", None) or _session_key(state)\n'
        "        _ACTIVE_TRANSLATION_TASKS.pop(_sk, None)\n"
        "        _revoke_unload_cancel(_sk)"
    )
    if old_finally not in text:
        raise SystemExit("038g: stop_translate finally anchor not found")
    text = text.replace(old_finally, new_finally, 1)
    return text


def main() -> int:
    if not GUI.is_file():
        print(f"找不到 {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    if MARKER in original:
        print("已是 PLAN-038g per-session unload，无需再改")
        return 0
    updated = apply(original)
    GUI.write_text(updated, encoding="utf-8")
    print(f"已写入 {GUI} ({MARKER})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

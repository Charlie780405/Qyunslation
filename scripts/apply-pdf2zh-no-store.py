#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-020：禁止浏览器缓存 index.html / config。

Gradio 把整棵组件树与事件索引（window.gradio_config）内嵌在 index.html 里，
而该响应既无 Cache-Control 也无 ETag/Last-Modified。组件树一改，旧页面的
fn_index 就与服务端错位：上传的无状态 POST 照样成功，事件回执却映射到
已不存在的组件上，表现为永久转圈且服务端零异常。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

MARKER = "_QyNoStoreMiddleware"

BLOCK = '''
# _qy_no_store_mw
from starlette.middleware import Middleware as _QyMiddleware
from starlette.middleware.base import BaseHTTPMiddleware as _QyBaseHTTPMiddleware

_QY_NO_STORE_PATHS = ("/", "/config", "/gradio_api/config")


class _QyNoStoreMiddleware(_QyBaseHTTPMiddleware):
    """index.html 内嵌 gradio_config，必须每次回源，否则旧组件树会残留。"""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path in _QY_NO_STORE_PATHS:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response


_QY_APP_KWARGS = {"middleware": [_QyMiddleware(_QyNoStoreMiddleware)]}


'''

ANCHOR = "def setup_gui(\n"

KWARG_LINE = re.compile(r"^[ \t]*app_kwargs=_QY_APP_KWARGS,\n", re.M)
ALLOWED_LINE = re.compile(
    r"^([ \t]*)allowed_paths=\[str\(p\) for p in pdf_preview_allowed_paths\],\n", re.M
)

EXPECTED_LAUNCH_SITES = 6


def apply(text: str) -> tuple[str, bool]:
    before = text

    if MARKER not in text:
        if ANCHOR not in text:
            print("WARNING: setup_gui anchor missing", file=sys.stderr)
            return text, False
        text = text.replace(ANCHOR, BLOCK.lstrip("\n") + ANCHOR, 1)

    # 先清空既有注入再按行重建，避免缩进前缀重叠导致的重复插入
    text = KWARG_LINE.sub("", text)
    text = ALLOWED_LINE.sub(
        lambda m: f"{m.group(0)}{m.group(1)}app_kwargs=_QY_APP_KWARGS,\n", text
    )

    return text, text != before


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"ERROR: {msg}", file=sys.stderr)
            errs += 1

    need(text.count("class _QyNoStoreMiddleware(") == 1, "middleware missing or duplicated")
    need(text.count("_QY_APP_KWARGS = {") == 1, "app kwargs missing or duplicated")
    need(
        text.count("app_kwargs=_QY_APP_KWARGS,") == EXPECTED_LAUNCH_SITES,
        f"expected {EXPECTED_LAUNCH_SITES} launch sites patched, "
        f"got {text.count('app_kwargs=_QY_APP_KWARGS,')}",
    )
    need(
        text.find("class _QyNoStoreMiddleware(") < text.find("def setup_gui("),
        "middleware must be defined before setup_gui",
    )
    try:
        compile(text, str(GUI), "exec")
    except SyntaxError as e:
        print(f"ERROR: syntax: {e}", file=sys.stderr)
        errs += 1
    return errs


def main() -> int:
    if not GUI.is_file():
        print(f"ERROR: missing {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    updated, changed = apply(original)
    if changed:
        GUI.write_text(updated, encoding="utf-8")
        print("patched:", GUI)
    else:
        print("already patched:", GUI)
    errs = verify(updated if changed else original)
    if errs:
        print(f"verify failed: {errs} error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

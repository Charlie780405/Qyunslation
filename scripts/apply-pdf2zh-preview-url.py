#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-020：预览不再内联 base64，改走 /gradio_api/file= URL。

实测证据（浏览器 Performance API）：
  queue/data 单条传输 789855 字节耗时 27s（≈29KB/s），随后的 queue/join
  从 550ms 劣化到 16.6s。789855 正是 590KB 图片 base64 后的长度。

原文一份、译文一份，upload 与 change 事件各推一次，慢链路上足以攒出
三分钟的「转圈」。改为让浏览器按 URL 直取，事件载荷从 ~790KB 降到几百字节，
且可被浏览器缓存。DOCX 经 mammoth 转换同样会内联 data URI，统一外置。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gui_extensions import set_literal  # noqa: E402

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

HELPER_MARKER = "_qy_file_url"

HELPER = '''
# _qy_preview_url
_QY_DATA_URI_PATTERN = r'src="data:(image/[^;",]+);base64,([^"]+)"'


def _qy_file_url(path) -> str:
    """Gradio 静态文件路由；调用方须保证路径落在 allowed_paths 内。"""
    from urllib.parse import quote

    return "/gradio_api/file=" + quote(str(Path(path).resolve()), safe="/")


def _qy_externalize_data_uris(html: str, out_dir: Path) -> str:
    """把内联的 base64 图片落盘并改成 URL 引用，避免预览载荷膨胀到 MB 级。"""
    if "base64," not in html:
        return html
    import base64 as _b64
    import re as _re

    seq = {"n": 0}

    def repl(m):
        seq["n"] += 1
        ext = m.group(1).split("/")[-1].split("+")[0] or "png"
        target = out_dir / f"_qy_preview_img_{seq['n']}.{ext}"
        try:
            target.write_bytes(_b64.b64decode(m.group(2)))
        except Exception:
            return m.group(0)
        return f'src="{_qy_file_url(target)}"'

    return _re.sub(_QY_DATA_URI_PATTERN, repl, html)


'''

ANCHOR = "def _qy_wrap_preview_html(body: str, title: str = \"\") -> str:"

IMG_OLD = '''        elif suf in __QY_IMAGE_EXT__:
            # Gradio 文件路径对浏览器不一定可访问；用 data URL
            import base64

            mime = _QY_IMAGE_MIME.get(suf, "application/octet-stream")
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            body = f'<img src="data:{mime};base64,{b64}" alt="{path.name}" style="max-width:100%;height:auto;"/>\''''.replace(
    "__QY_IMAGE_EXT__", set_literal("image")
)

IMG_NEW = '''        elif suf in __QY_IMAGE_EXT__:
            # 走静态路由而非 data URL：内联 base64 会让事件载荷膨胀约 1.34 倍，
            # 慢链路上单张图就要几十秒才推得完，表现为预览长时间转圈。
            body = (
                f'<img src="{_qy_file_url(path)}" alt="{_html_escape(path.name)}"'
                ' loading="lazy" style="max-width:100%;height:auto;"/>'
            )'''.replace("__QY_IMAGE_EXT__", set_literal("image"))

DOCX_OLD = """        elif suf in {".docx", ".doc"}:
            body = _qy_docx_to_html(path)
            if not body.strip():
                body = "<p>（未能从 Word 提取预览内容，请直接下载）</p>\""""

DOCX_NEW = """        elif suf in {".docx", ".doc"}:
            body = _qy_externalize_data_uris(_qy_docx_to_html(path), path.parent)
            if not body.strip():
                body = "<p>（未能从 Word 提取预览内容，请直接下载）</p>\""""


def apply(text: str) -> tuple[str, bool]:
    changed = False

    if "def _qy_file_url(" not in text:
        if ANCHOR not in text:
            print("WARNING: preview helper anchor missing", file=sys.stderr)
        else:
            text = text.replace(ANCHOR, HELPER.lstrip("\n") + ANCHOR, 1)
            changed = True

    for old, new in ((IMG_OLD, IMG_NEW), (DOCX_OLD, DOCX_NEW)):
        if old in text:
            text = text.replace(old, new, 1)
            changed = True

    return text, changed


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"ERROR: {msg}", file=sys.stderr)
            errs += 1

    need(text.count("def _qy_file_url(") == 1, "file url helper missing or duplicated")
    need(
        text.count("def _qy_externalize_data_uris(") == 1,
        "data uri externalizer missing or duplicated",
    )
    need(IMG_OLD not in text, "image preview still inlines base64")
    need(
        'b64 = base64.b64encode(path.read_bytes()).decode("ascii")' not in text,
        "base64 inlining still present in preview",
    )
    need(IMG_NEW in text, "image preview not switched to file url")
    need(DOCX_NEW in text, "docx preview not externalizing data uris")
    need(
        text.find("def _qy_file_url(") < text.find("def _qy_preview_payload("),
        "helper must be defined before _qy_preview_payload",
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

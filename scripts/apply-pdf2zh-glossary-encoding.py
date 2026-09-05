#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-020：术语表 CSV 编码兜底。

`chardet.detect()` 对空文件或无法识别的内容返回 encoding=None，
`bytes.decode(None)` 抛 TypeError；在生成器上下文里则冒成 StopIteration。
两处 except 均未覆盖，异常在 build_ui_inputs 阶段逃逸，早于任何日志，
Gradio 只回一个 success=False 且 error 为空的包，前端永久转圈。
"""
from __future__ import annotations

import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

HELPER_MARKER = "_qy_decode_glossary_bytes"

HELPER = '''
# _qy_glossary_decode
def _qy_decode_glossary_bytes(data: bytes, name: str = "术语表") -> str:
    """按 chardet 猜测 + 常见编码依次尝试解码，失败时给出可执行的提示。"""
    if not data:
        raise gr.Error(f"{name}是空文件，请上传含 source,target 两列的 CSV")
    try:
        guess = chardet.detect(data).get("encoding")
    except Exception:
        guess = None
    seen = []
    for enc in (guess, "utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        if not enc or enc in seen:
            continue
        seen.append(enc)
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise gr.Error(f"无法识别{name}的编码，请另存为 UTF-8 编码的 CSV 后重试")


'''

BUILD_OLD = '''            f = io.StringIO(file.decode(chardet.detect(file)["encoding"]))'''
BUILD_NEW = '''            f = io.StringIO(_qy_decode_glossary_bytes(file))'''

BUILD_EXCEPT_OLD = """        except (UnicodeDecodeError, csv.Error, KeyError) as e:
            logger.error(f"Error processing glossary file: {e}")
            gr.Error(f"Failed to process glossary file: {e}")"""
BUILD_EXCEPT_NEW = """        except gr.Error:
            raise
        except (UnicodeDecodeError, csv.Error, KeyError, TypeError, ValueError) as e:
            logger.error(f"Error processing glossary file: {e}")
            raise gr.Error(f"术语表解析失败：{e}") from e"""

CHANGE_OLD_REAL = '''                file_encoding = chardet.detect(file)["encoding"]
                content = file.decode(file_encoding).replace("\\r\\n", "\\n").strip()'''
CHANGE_NEW_REAL = '''                content = (
                    _qy_decode_glossary_bytes(file).replace("\\r\\n", "\\n").strip()
                )'''

SKIP_OLD = """                    next(csvreader)  # Skip header"""
SKIP_NEW = """                    next(csvreader, None)  # Skip header (空文件不得抛 StopIteration)"""

ANCHOR = "def _build_glossary_list(glossary_file, service_name=None):"


def apply(text: str) -> tuple[str, bool]:
    changed = False

    if HELPER_MARKER + "(data" not in text:
        if ANCHOR not in text:
            print("WARNING: _build_glossary_list anchor missing", file=sys.stderr)
        else:
            text = text.replace(ANCHOR, HELPER.lstrip("\n") + ANCHOR, 1)
            changed = True

    for old, new in (
        (BUILD_OLD, BUILD_NEW),
        (BUILD_EXCEPT_OLD, BUILD_EXCEPT_NEW),
        (CHANGE_OLD_REAL, CHANGE_NEW_REAL),
        (SKIP_OLD, SKIP_NEW),
    ):
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

    need(text.count("def _qy_decode_glossary_bytes(") == 1, "helper missing or duplicated")
    need(BUILD_OLD not in text, "_build_glossary_list still uses raw chardet decode")
    need(CHANGE_OLD_REAL not in text, "on_glossary_file_change still uses raw chardet decode")
    need(SKIP_OLD not in text, "next(csvreader) still unguarded")
    need("raise gr.Error(f\"术语表解析失败：{e}\") from e" in text, "glossary error not raised")
    need(
        'chardet.detect(file)["encoding"]' not in text,
        "raw chardet.detect(file) call still present",
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

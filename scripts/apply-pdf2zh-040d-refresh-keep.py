#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-040d：刷新/关页不取消翻译；仅 stop_translate_file（手动停止）可取消。

须在 apply-pdf2zh-038g-session-cancel.py 之后跑（改写 unload 钩子体）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
MARKER = "PLAN-040d: refresh must NOT cancel"

NEW_FN = '''def _cancel_active_translation_on_unload(request=None) -> None:
    """PLAN-038g: per-session unload cancel
    PLAN-040d: refresh must NOT cancel; only stop_translate_file cancels.
    """
    session_key = _session_key(request=request)
    # Drop any pending grace cancel so a refresh cannot kill the job later.
    _revoke_unload_cancel(session_key)
    logger.info(
        "Browser unload: keeping translation for session %s (PLAN-040d; use Stop to cancel)",
        session_key,
    )


'''


def apply(text: str) -> str:
    if MARKER in text and "keeping translation for session" in text:
        return text

    pat = re.compile(
        r"def _cancel_active_translation_on_unload\(request=None\) -> None:.*?"
        r"(?=\nasync def stop_translate_file)",
        re.MULTILINE | re.DOTALL,
    )
    if not pat.search(text):
        # legacy signature without request=
        pat = re.compile(
            r"def _cancel_active_translation_on_unload\(\) -> None:.*?"
            r"(?=\nasync def stop_translate_file)",
            re.MULTILINE | re.DOTALL,
        )
    if not pat.search(text):
        raise SystemExit("040d: unload cancel function not found")
    return pat.sub(NEW_FN, text, count=1)


def main() -> int:
    if not GUI.is_file():
        print(f"ERROR: missing {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    updated = apply(original)
    if updated == original:
        print("已是 PLAN-040d refresh-keep，无需再改")
        return 0
    GUI.write_text(updated, encoding="utf-8")
    print(f"patched {GUI} ({MARKER})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

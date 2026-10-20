#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-080c：给 BabelDOC 的 FontMapper 安装统一字体策略。

在 ``babeldoc/format/pdf/document_il/utils/fontmap.py`` 末尾追加一个带标记的块，调用
``qyunslation.structure.font_policy.install(FontMapper)``。策略本身由环境变量
``QYUNSLATION_FONT_POLICY`` 控制，默认 ``off``，所以装上补丁不改变任何输出。
导入失败时静默跳过（补丁失败的结果是"字体和以前一样"，不是"文字消失"，SK-Q005）。

幂等：已有标记则不改。必须排在 apply-pdf2zh-fidelity-033h.py 之后（后者改 FontMapper.map 的方法体）。
"""
from __future__ import annotations

import sys
from pathlib import Path

SITE = Path.home() / ".local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
FONTMAP = SITE / "babeldoc/format/pdf/document_il/utils/fontmap.py"
MARKER = "_QY_080C_FONT_POLICY"

BLOCK = f'''

# {MARKER}
try:
    from qyunslation.structure.font_policy import install as _qy_080c_install

    _qy_080c_install(FontMapper)
except Exception:  # 补丁失败时保持原字体行为
    pass
'''


def patch_fontmap(text: str) -> tuple[str, bool]:
    if MARKER in text:
        return text, False
    if "class FontMapper" not in text:
        return text, False
    return text.rstrip("\n") + "\n" + BLOCK, True


def main() -> int:
    if not FONTMAP.is_file():
        print(f"SKIP missing {FONTMAP}", file=sys.stderr)
        return 0
    text = FONTMAP.read_text(encoding="utf-8")
    new, changed = patch_fontmap(text)
    if changed:
        FONTMAP.write_text(new, encoding="utf-8")
        print(f"patched {FONTMAP}")
    else:
        print(f"unchanged {FONTMAP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

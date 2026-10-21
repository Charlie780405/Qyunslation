# SPDX-License-Identifier: MPL-2.0
"""表内中文字体解析：拒绝可变字体（默认实例是 Thin），保证汉字与数字一样深。

``.env`` 里的 ``QYUNSLATION_FONT`` 可能指向 ``NotoSansSC.ttf``（可变字体，fvar 默认 wght=100）。pymupdf/fontTools 子集
不会应用可变轴，嵌进表里的汉字就是 Thin，比 Helvetica 数字淡一大截。这里统一把它换成静态 Regular/Bold。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_FONT_HOME = Path(os.environ.get("QYUNSLATION_FONT_HOME", "/home/dev/.fonts"))
_BABELDOC_FONTS = Path(os.environ.get("QYUNSLATION_BABELDOC_FONT_DIR", "/home/dev/.cache/babeldoc/fonts"))


@lru_cache(maxsize=32)
def is_variable_or_thin(path: str) -> bool:
    """fvar 存在，或 OS/2 字重 < 300（Thin/ExtraLight）都不能当正文字体。读不出来按"可用"处理。"""
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(path, lazy=True, fontNumber=0)
        try:
            if "fvar" in font:
                return True
            weight = int(font["OS/2"].usWeightClass) if "OS/2" in font else 400
            return weight < 300
        finally:
            font.close()
    except Exception:  # noqa: BLE001
        return False


def _static_candidates(bold: bool) -> list[Path]:
    face = "Bold" if bold else "Regular"
    return [
        _FONT_HOME / f"NotoSansSC-{face}.otf",
        _BABELDOC_FONTS / f"SourceHanSansCN-{face}.ttf",
    ]


def resolve_static_cjk(configured: str | os.PathLike[str] | None, *, bold: bool = False) -> Path:
    """返回可用于表内落笔的静态中文字体路径。配置值可用就用它，可变/Thin 则换成静态字面。"""
    path = Path(configured) if configured else None
    if path is not None and path.is_file() and not is_variable_or_thin(str(path)):
        return path
    for candidate in _static_candidates(bold):
        if candidate.is_file() and not is_variable_or_thin(str(candidate)):
            return candidate
    return path or _static_candidates(bold)[0]

# SPDX-License-Identifier: MPL-2.0
"""PLAN-080c：统一译文字体。

BabelDOC 的 ``FontMapper.map`` 在目标语言为 ``zh`` 时会合并多语种字体表，于是同一份译文里：
拉丁字符落到 NotoSerif，汉字落到思源宋体，斜体汉字落到霞鹜文楷，粗体又是另一套。这里把选择
收敛为：同一个字体族（默认思源宋体 SourceHanSerifCN，画像明确写 sans-serif 时用思源黑体），
只按粗体区分 Regular / Bold，不再按斜体换字体。字体族里没有该字形时回落到原行为，不删字。

开关 ``QYUNSLATION_FONT_POLICY``：``off``（默认，行为不变）/ ``unified``。
通过 ``install(FontMapper)`` 包装 ``map``，不改方法体；包装本身出错时同样回落到原行为。
"""
from __future__ import annotations

import os
from typing import Any

from .font_style import infer_bold

MODE_ENV = "QYUNSLATION_FONT_POLICY"
_MARKER = "_qy_080c_font_policy"

# BabelDOC 的 PrimaryFontFamily：SERIF=1，SANS_SERIF=2；这里不导入它，避免依赖引擎包。
_SANS_SERIF = 2

SERIF_FONTS = {False: "SourceHanSerifCN-Regular.ttf", True: "SourceHanSerifCN-Bold.ttf"}
SANS_FONTS = {False: "SourceHanSansCN-Regular.ttf", True: "SourceHanSansCN-Bold.ttf"}


def font_policy_mode() -> str:
    value = (os.environ.get(MODE_ENV) or "off").strip().lower()
    return "unified" if value == "unified" else "off"


def _is_bold(font: Any) -> bool:
    if hasattr(font, "is_bold"):  # pymupdf.Font
        return bool(font.is_bold)
    name = getattr(font, "name", None) or getattr(font, "font_id", "") or ""
    return bool(getattr(font, "bold", False)) or infer_bold(name)


def unified_font(mapper: Any, original_font: Any, char_unicode: str) -> Any | None:
    """返回统一字体族里能画出该字符的字体；没有则返回 None（交给原逻辑）。"""
    if len(char_unicode) != 1:
        return None
    sans = int(getattr(mapper, "primary_font_family", 0) or 0) == _SANS_SERIF
    table = SANS_FONTS if sans else SERIF_FONTS
    font = mapper.fontid2font.get(table[_is_bold(original_font)])
    if font is not None and font.has_glyph(ord(char_unicode)):
        return font
    return None


def install(mapper_cls: Any) -> bool:
    """包装 ``mapper_cls.map``；重复调用无副作用。返回是否新安装。"""
    if getattr(mapper_cls, _MARKER, False):
        return False
    original = mapper_cls.map

    def map_with_policy(self, original_font, char_unicode):  # noqa: ANN001
        if font_policy_mode() == "unified":
            try:
                font = unified_font(self, original_font, char_unicode)
            except Exception:
                font = None
            if font is not None:
                return font
        return original(self, original_font, char_unicode)

    mapper_cls.map = map_with_policy
    setattr(mapper_cls, _MARKER, True)
    return True

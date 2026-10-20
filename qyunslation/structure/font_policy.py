# SPDX-License-Identifier: MPL-2.0
"""PLAN-080c：统一译文字体。

BabelDOC 的 ``FontMapper.map`` 在目标语言为 ``zh`` 时会合并多语种字体表，于是同一份译文里：
拉丁字符落到 NotoSerif，汉字落到思源宋体，斜体汉字落到霞鹜文楷，粗体又是另一套。这里把选择
收敛为：同一个字体族（默认思源宋体 SourceHanSerifCN；FAMILY=profile 时画像写 sans-serif 用思源黑体），
只按粗体区分 Regular / Bold，不再按斜体换字体。字体族里没有该字形时回落到原行为，不删字。

开关 ``QYUNSLATION_FONT_POLICY``：``off``（默认，行为不变）/ ``unified``。
字体族 ``QYUNSLATION_FONT_POLICY_FAMILY``：``serif``（默认，D2 选定思源宋体，所有画像一致）/
``profile``（沿用画像里写的 primary_font_family：sans-serif 用思源黑体，其余用思源宋体）。
通过 ``install(FontMapper)`` 包装 ``map``，不改方法体；包装本身出错时同样回落到原行为。
"""
from __future__ import annotations

import os
from typing import Any

from .font_style import infer_bold

MODE_ENV = "QYUNSLATION_FONT_POLICY"
FAMILY_ENV = "QYUNSLATION_FONT_POLICY_FAMILY"
_MARKER = "_qy_080c_font_policy"

# BabelDOC 的 PrimaryFontFamily：SERIF=1，SANS_SERIF=2；这里不导入它，避免依赖引擎包。
_SANS_SERIF = 2

SERIF_FONTS = {False: "SourceHanSerifCN-Regular.ttf", True: "SourceHanSerifCN-Bold.ttf"}
SANS_FONTS = {False: "SourceHanSansCN-Regular.ttf", True: "SourceHanSansCN-Bold.ttf"}


def font_policy_mode() -> str:
    value = (os.environ.get(MODE_ENV) or "off").strip().lower()
    return "unified" if value == "unified" else "off"


def font_policy_family() -> str:
    value = (os.environ.get(FAMILY_ENV) or "serif").strip().lower()
    return "profile" if value == "profile" else "serif"


def _is_bold(font: Any) -> bool:
    if hasattr(font, "is_bold"):  # pymupdf.Font
        return bool(font.is_bold)
    name = getattr(font, "name", None) or getattr(font, "font_id", "") or ""
    return bool(getattr(font, "bold", False)) or infer_bold(name)


def _targets_simplified_chinese(mapper: Any) -> bool:
    """只对目标语言为简体中文的翻译生效。

    BabelDOC 的字体表在 lang_out=en 时同样包含思源字体，不判断目标语言的话，中译英的英文译文
    也会被改成思源宋体并丢掉斜体；繁体/港澳的字体（SourceHanSerifTW/HK）也不是这里的统一对象。
    取不到目标语言时（替身、旧版引擎）按"生效"处理，行为与 v1 一致。
    """
    config = getattr(mapper, "translation_config", None)
    lang = str(getattr(config, "lang_out", "") or "").strip().lower().replace("_", "-")
    return lang == "" or lang in {"zh", "zh-cn", "zh-hans"}


def unified_font(mapper: Any, original_font: Any, char_unicode: str) -> Any | None:
    """返回统一字体族里能画出该字符的字体；没有则返回 None（交给原逻辑）。"""
    if len(char_unicode) != 1 or not _targets_simplified_chinese(mapper):
        return None
    sans = font_policy_family() == "profile" and int(getattr(mapper, "primary_font_family", 0) or 0) == _SANS_SERIF
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

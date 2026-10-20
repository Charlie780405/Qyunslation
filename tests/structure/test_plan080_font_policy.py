# SPDX-License-Identifier: MPL-2.0
"""PLAN-080c：统一译文字体策略（不依赖 BabelDOC，用替身验证选择逻辑）。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qyunslation.structure import font_policy as fp


class FakeFont:
    def __init__(self, name: str, chars: str = "", cjk: bool = True):
        self.name = name
        self.chars = set(chars)
        self.cjk = cjk

    def has_glyph(self, code: int) -> bool:
        ch = chr(code)
        if "一" <= ch <= "鿿":
            return self.cjk
        return ch.isascii()  # 思源字库含拉丁字母，足以覆盖测试字符


def make_mapper_class(primary: int = 1, with_cn: bool = True):
    fonts = {
        "NotoSerif-Regular.ttf": FakeFont("noto", cjk=False),
        "LXGWWenKaiGB-Regular.1.520.ttf": FakeFont("lxgw"),
    }
    if with_cn:
        for key in (*fp.SERIF_FONTS.values(), *fp.SANS_FONTS.values()):
            fonts[key] = FakeFont(key)

    class Mapper:
        def __init__(self):
            self.primary_font_family = primary
            self.fontid2font = fonts

        def map(self, original_font, char_unicode):
            return "legacy"

    return Mapper


@pytest.fixture(autouse=True)
def _mode(monkeypatch):
    monkeypatch.setenv(fp.MODE_ENV, "unified")


def italic_arial():
    return SimpleNamespace(bold=False, italic=True, name="Arial-ItalicMT")


def bold_arial():
    return SimpleNamespace(bold=False, italic=False, name="Arial-BoldMT")


def test_default_mode_is_off(monkeypatch):
    monkeypatch.delenv(fp.MODE_ENV, raising=False)
    assert fp.font_policy_mode() == "off"
    cls = make_mapper_class()
    fp.install(cls)
    assert cls().map(italic_arial(), "中") == "legacy"


def test_unknown_mode_value_is_off(monkeypatch):
    monkeypatch.setenv(fp.MODE_ENV, "enabled-please")
    assert fp.font_policy_mode() == "off"


def test_italic_chinese_uses_the_same_family_not_script_font():
    cls = make_mapper_class()
    fp.install(cls)
    font = cls().map(italic_arial(), "中")
    assert font.name == "SourceHanSerifCN-Regular.ttf"


def test_latin_in_translation_uses_the_same_family():
    cls = make_mapper_class()
    fp.install(cls)
    assert cls().map(italic_arial(), "B").name == "SourceHanSerifCN-Regular.ttf"


def test_bold_is_the_only_variant():
    cls = make_mapper_class()
    fp.install(cls)
    assert cls().map(bold_arial(), "中").name == "SourceHanSerifCN-Bold.ttf"
    pymupdf_like = SimpleNamespace(is_bold=True, is_italic=True)
    assert cls().map(pymupdf_like, "A").name == "SourceHanSerifCN-Bold.ttf"


def test_sans_serif_profile_still_gets_serif_by_default():
    """D2/D5：思源宋体适用所有画像，书信与 IND 递交资料画像（sans-serif）也不例外。"""
    cls = make_mapper_class(primary=2)
    fp.install(cls)
    assert fp.font_policy_family() == "serif"
    assert cls().map(italic_arial(), "中").name == "SourceHanSerifCN-Regular.ttf"


def test_profile_family_option_respects_sans_serif(monkeypatch):
    monkeypatch.setenv(fp.FAMILY_ENV, "profile")
    cls = make_mapper_class(primary=2)
    fp.install(cls)
    assert cls().map(italic_arial(), "中").name == "SourceHanSansCN-Regular.ttf"
    serif_profile = make_mapper_class(primary=1)
    fp.install(serif_profile)
    assert serif_profile().map(italic_arial(), "中").name == "SourceHanSerifCN-Regular.ttf"


def test_unknown_family_value_means_serif(monkeypatch):
    monkeypatch.setenv(fp.FAMILY_ENV, "comic-sans")
    assert fp.font_policy_family() == "serif"


def test_missing_glyph_falls_back_to_legacy_mapping():
    cls = make_mapper_class()
    cls_inst = cls()
    cls_inst.fontid2font[fp.SERIF_FONTS[False]].has_glyph = lambda code: False
    fp.install(cls)
    assert cls_inst.map(italic_arial(), "中") == "legacy"


def test_family_not_loaded_falls_back_to_legacy_mapping():
    """目标语言不是中文时字体表里没有思源，行为不变。"""
    cls = make_mapper_class(with_cn=False)
    fp.install(cls)
    assert cls().map(italic_arial(), "中") == "legacy"


def test_multi_character_input_is_left_to_legacy():
    cls = make_mapper_class()
    fp.install(cls)
    assert cls().map(italic_arial(), "ab") == "legacy"


def test_install_is_idempotent_and_wrapper_errors_fall_back():
    cls = make_mapper_class()
    assert fp.install(cls) is True
    assert fp.install(cls) is False
    broken = cls()
    broken.fontid2font = None  # 触发包装内部异常
    assert broken.map(italic_arial(), "中") == "legacy"


def test_policy_applies_only_to_simplified_chinese_targets():
    from types import SimpleNamespace

    for lang, applies in (("zh", True), ("zh-CN", True), ("zh_cn", True), ("en", False), ("zh-TW", False), ("ja", False)):
        cls = make_mapper_class()
        fp.install(cls)
        mapper = cls()
        mapper.translation_config = SimpleNamespace(lang_out=lang)
        picked = mapper.map(italic_arial(), "中")
        assert (picked != "legacy") is applies, lang

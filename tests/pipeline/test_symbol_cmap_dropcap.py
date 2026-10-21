from qyunslation.structure import pdf_symbol_cmap as sc
from qyunslation.structure import pdf_dropcap as dc


def test_symbol_font_fixes_cover_plusminus_ge_copyright():
    assert sc.SYMBOL_FONT_FIXES["AdvPSSymbol"][150] == "\u00b1"
    assert sc.SYMBOL_FONT_FIXES["AdvPSSymbol"][135] == "\u2265"
    assert sc.SYMBOL_FONT_FIXES["AdvPSSym"][170] == "\u00a9"


def test_build_to_unicode_maps_overrides():
    cmap = sc.build_to_unicode(32, [500] * 3, {33: "\u00b1"})
    data = cmap if isinstance(cmap, bytes) else str(cmap).encode()
    assert b"00B1" in data.upper()


def test_dropcap_api_present():
    for name in ("detect_dropcaps", "normalize_dropcaps", "emphasize_zh_first_char", "finish_dropcaps"):
        assert callable(getattr(dc, name))


def test_decorative_unmapped_inherited():
    from qyunslation.structure.text_sanitize import is_decorative_unmapped_inherited as f
    assert f("a\x01b", "a\ufffdb")
    assert not f("clean", "a\ufffdb")
    assert not f("a\x01b", "a\ufffd\ufffd\ufffdb")
    assert f("a\x01b", "a\ufffdb a\ufffdb", copies=2)

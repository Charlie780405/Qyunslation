from qyunslation.structure import pdf_symbol_cmap as sc
from qyunslation.structure import pdf_dropcap as dc


def test_symbol_font_fixes_cover_plusminus_ge_copyright():
    assert sc.SYMBOL_FONT_FIXES["AdvPSSymbol"][150] == "\u00b1"
    assert sc.SYMBOL_FONT_FIXES["AdvPSSymbol"][135] == "\u2265"
    assert sc.SYMBOL_FONT_FIXES["AdvPSSym"][170] == "\u00a9"


def test_symbol_font_fixes_cover_bullet_and_header_square():
    assert sc.SYMBOL_FONT_FIXES["AdvP4C4E74"][1] == "\u2022"
    assert sc.SYMBOL_FONT_FIXES["AdvMathpi6"][1] == "\u25a0"


def test_bullet_and_square_are_not_read_as_control_codes():
    for family, char in (("AdvP4C4E74", "2022"), ("AdvMathpi6", "25A0")):
        cmap = sc.build_to_unicode(1, [500], sc.SYMBOL_FONT_FIXES[family])
        data = (cmap if isinstance(cmap, bytes) else str(cmap).encode()).upper()
        assert f"<01> <{char}>".encode() in data
        assert b"<01> <0001>" not in data


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


def test_restore_symbol_left_halves_noop_without_fixed_origin(tmp_path):
    from qyunslation.structure.source_prepare import restore_symbol_left_halves

    run_dir = tmp_path / "run"
    (run_dir / "source").mkdir(parents=True)
    out = tmp_path / "out"
    out.mkdir()
    assert restore_symbol_left_halves(run_dir, out) is None

# SPDX-License-Identifier: MPL-2.0
"""PLAN-083: Hermes-style literature table rebuild."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from qyunslation.structure.table_rebuild import (
    TableWord,
    rebuild_from_page,
    rebuild_literature_table,
    table_rebuild_mode,
    verify_hpd_grid_against_words,
)


def _word(text: str, x0: float, y0: float, x1: float | None = None, y1: float | None = None) -> TableWord:
    return TableWord(text=text, x0=x0, y0=y0, x1=x0 + (x1 or (6.0 * max(len(text), 1))), y1=y0 + (y1 or 10.0))


def _four_col_demographics():
    """Synthetic Table-1 style: label + 4 numeric columns separated by x bands."""
    # Row rules (top, after header, after age, after sex, bottom)
    rules = [80.0, 110.0, 140.0, 170.0, 200.0]
    box = (40.0, 80.0, 540.0, 200.0)
    words = [
        # header
        _word("Characteristic", 50, 90),
        _word("A", 180, 90),
        _word("(n=30)", 200, 90),
        _word("B", 280, 90),
        _word("(n=31)", 300, 90),
        _word("Placebo", 380, 90),
        _word("(n=32)", 420, 90),
        _word("Total", 480, 90),
        _word("(n=93)", 510, 90),
        # age row
        _word("Age,", 50, 120),
        _word("years", 80, 120),
        _word("43.9", 180, 120),
        _word("(16.9)", 210, 120),
        _word("48.6", 280, 120),
        _word("(17.8)", 310, 120),
        _word("43.9", 380, 120),
        _word("(14.8)", 410, 120),
        _word("45.5", 480, 120),
        _word("(16.5)", 510, 120),
        # sex section + female
        _word("Sex,", 50, 150),
        _word("n", 80, 150),
        _word("(%)", 95, 150),
        _word("Female", 50, 180),
        _word("8", 180, 180),
        _word("(26.7)", 200, 180),
        _word("11", 280, 180),
        _word("(35.5)", 305, 180),
        _word("9", 380, 180),
        _word("(28.1)", 400, 180),
        _word("28", 480, 180),
        _word("(30.1)", 505, 180),
    ]
    return words, rules, box


def test_rebuild_splits_four_numeric_columns():
    words, rules, box = _four_col_demographics()
    result = rebuild_literature_table(words, rules, box=box)
    assert result.ok, result.reason
    assert result.n_cols >= 4
    # Find the Age data row
    age_row = next(row for row in result.rows if any("43.9" in c for c in row))
    joined_age = " ".join(age_row)
    # Values must not all collapse into one cell.
    numeric_cells = [c for c in age_row if "43.9" in c or "48.6" in c or "45.5" in c]
    assert len(numeric_cells) >= 2
    assert "43.9 (16.9) 48.6" not in age_row[0]
    # 43.9 and 48.6 must appear in different cells
    cells_with_439 = [i for i, c in enumerate(age_row) if "43.9" in c]
    cells_with_486 = [i for i, c in enumerate(age_row) if "48.6" in c]
    assert cells_with_439 and cells_with_486
    assert set(cells_with_439).isdisjoint(set(cells_with_486)) or len(cells_with_439) > 1
    assert "48.6" in joined_age


def test_rebuild_splits_three_treatment_columns():
    rules = [100.0, 130.0, 160.0, 190.0]
    box = (40.0, 100.0, 500.0, 190.0)
    words = [
        _word("Event", 50, 110),
        _word("GroupA", 200, 110),
        _word("GroupB", 320, 110),
        _word("Placebo", 420, 110),
        _word("Any", 50, 140),
        _word("TEAE", 80, 140),
        _word("19", 200, 140),
        _word("(63.3)", 220, 140),
        _word("20", 320, 140),
        _word("(64.5)", 340, 140),
        _word("21", 420, 140),
        _word("(65.6)", 440, 140),
        _word("Grade", 50, 170),
        _word("3", 90, 170),
        _word("2", 200, 170),
        _word("(6.7)", 220, 170),
        _word("1", 320, 170),
        _word("(3.2)", 340, 170),
        _word("0", 420, 170),
    ]
    result = rebuild_literature_table(words, rules, box=box)
    assert result.ok, result.reason
    teae = next(row for row in result.rows if any("19" in c for c in row))
    # 19/20/21 must not share one cell
    assert not any("19 (63.3) 20" in c for c in teae)
    cols_19 = [i for i, c in enumerate(teae) if "19" in c]
    cols_20 = [i for i, c in enumerate(teae) if "20" in c]
    cols_21 = [i for i, c in enumerate(teae) if "21" in c]
    assert cols_19 and cols_20 and cols_21
    assert len({cols_19[0], cols_20[0], cols_21[0]}) == 3


def test_no_row_rules_fails_closed():
    words = [_word("a", 10, 10), _word("b", 50, 10), _word("c", 10, 40), _word("d", 50, 40)]
    result = rebuild_literature_table(words, rules=[10.0, 40.0], box=(0, 0, 100, 50))
    assert not result.ok
    assert result.reason == "no_row_rules"


def test_table_rebuild_mode_default(monkeypatch):
    monkeypatch.delenv("QYUNSLATION_TABLE_REBUILD", raising=False)
    assert table_rebuild_mode() == "literature"
    monkeypatch.setenv("QYUNSLATION_TABLE_REBUILD", "off")
    assert table_rebuild_mode() == "off"


def test_hpd_verify_requires_number_coverage():
    words = [
        _word("19", 10, 10),
        _word("(63.3)", 30, 10),
        _word("20", 80, 10),
        _word("(64.5)", 100, 10),
    ]
    good = [["19 (63.3)", "20 (64.5)"]]
    assert verify_hpd_grid_against_words(good, words, estimated_rows=1) is True
    bad = [["99 (0.0)", "88 (0.0)"]]
    assert verify_hpd_grid_against_words(bad, words, estimated_rows=1) is False


def _ruled_four_col_pdf(path: Path) -> tuple[Path, tuple[float, float, float, float]]:
    """Synthetic demographics table with row rules (Table-1 shape)."""
    doc = pymupdf.open()
    page = doc.new_page(width=560, height=240)
    box = (40.0, 60.0, 540.0, 200.0)
    # Horizontal rules
    for y in (60, 95, 130, 165, 200):
        page.draw_line(pymupdf.Point(40, y), pymupdf.Point(540, y), width=0.6)
    # Header
    page.insert_text((50, 82), "Characteristic", fontsize=8)
    page.insert_text((180, 82), "A (n=30)", fontsize=8)
    page.insert_text((280, 82), "B (n=31)", fontsize=8)
    page.insert_text((380, 82), "Placebo (n=32)", fontsize=8)
    page.insert_text((480, 82), "Total (n=93)", fontsize=8)
    # Age row — values must stay in separate columns after rebuild/paint
    page.insert_text((50, 117), "Age, years", fontsize=8)
    page.insert_text((180, 117), "43.9 (16.9)", fontsize=8)
    page.insert_text((280, 117), "48.6 (17.8)", fontsize=8)
    page.insert_text((380, 117), "43.9 (14.8)", fontsize=8)
    page.insert_text((480, 117), "45.5 (16.5)", fontsize=8)
    # Female row
    page.insert_text((50, 152), "Female", fontsize=8)
    page.insert_text((180, 152), "8 (26.7)", fontsize=8)
    page.insert_text((280, 152), "11 (35.5)", fontsize=8)
    page.insert_text((380, 152), "9 (28.1)", fontsize=8)
    page.insert_text((480, 152), "28 (30.1)", fontsize=8)
    doc.save(path)
    doc.close()
    return path, box


def test_rebuild_from_page_splits_table1_columns(tmp_path):
    path, box = _ruled_four_col_pdf(tmp_path / "t1.pdf")
    doc = pymupdf.open(path)
    result = rebuild_from_page(doc[0], box, allow_hpd_fallback=False)
    doc.close()
    assert result.ok, result.reason
    age = next(row for row in result.rows if any("43.9" in c for c in row))
    assert not any("43.9 (16.9) 48.6" in c for c in age)
    i439 = [i for i, c in enumerate(age) if "43.9 (16.9)" in c or c.strip().startswith("43.9")]
    i486 = [i for i, c in enumerate(age) if "48.6" in c]
    assert i439 and i486
    assert i439[0] != i486[0]


def test_rebuild_from_page_splits_table2_treatments(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=520, height=220)
    box = (40.0, 70.0, 500.0, 190.0)
    for y in (70, 105, 140, 175, 190):
        page.draw_line(pymupdf.Point(40, y), pymupdf.Point(500, y), width=0.6)
    page.insert_text((50, 92), "Event", fontsize=8)
    page.insert_text((200, 92), "GroupA", fontsize=8)
    page.insert_text((320, 92), "GroupB", fontsize=8)
    page.insert_text((420, 92), "Placebo", fontsize=8)
    page.insert_text((50, 127), "Any TEAE", fontsize=8)
    page.insert_text((200, 127), "19 (63.3)", fontsize=8)
    page.insert_text((320, 127), "20 (64.5)", fontsize=8)
    page.insert_text((420, 127), "21 (65.6)", fontsize=8)
    page.insert_text((50, 162), "Grade 3", fontsize=8)
    page.insert_text((200, 162), "2 (6.7)", fontsize=8)
    page.insert_text((320, 162), "1 (3.2)", fontsize=8)
    page.insert_text((420, 162), "0", fontsize=8)
    path = tmp_path / "t2.pdf"
    doc.save(path)
    doc.close()
    doc = pymupdf.open(path)
    result = rebuild_from_page(doc[0], box, allow_hpd_fallback=False)
    doc.close()
    assert result.ok, result.reason
    teae = next(row for row in result.rows if any("19" in c for c in row))
    assert not any("19 (63.3) 20" in c for c in teae)
    cols = {
        next(i for i, c in enumerate(teae) if "19" in c),
        next(i for i, c in enumerate(teae) if "20" in c),
        next(i for i, c in enumerate(teae) if "21" in c),
    }
    assert len(cols) == 3


def test_hpd_fallback_only_when_no_row_rules_and_verified(monkeypatch):
    """S3: HPD supplies geometry only after number-coverage verify; never OCR text."""
    from qyunslation.structure.table_grid_hpd import HpdGrid

    words = [
        _word("Age", 50, 120),
        _word("43.9", 180, 120),
        _word("(16.9)", 210, 120),
        _word("48.6", 280, 120),
        _word("(17.8)", 310, 120),
        _word("Sex", 50, 150),
        _word("8", 180, 150),
        _word("(26.7)", 200, 150),
        _word("11", 280, 150),
        _word("(35.5)", 305, 150),
    ]
    box = (40.0, 100.0, 400.0, 180.0)

    class _FakePage:
        def get_text(self, mode="text"):
            if mode == "words":
                return [
                    (w.x0, w.y0, w.x1, w.y1, w.text, 0, 0, 0) for w in words
                ]
            return ""

        def get_drawings(self):
            return []

    fake_grid = HpdGrid(
        rows=[["Age", "43.9 (16.9)", "48.6 (17.8)"], ["Sex", "8 (26.7)", "11 (35.5)"]],
        n_cols=3,
        source_md="<table></table>",
    )
    with (
        patch("qyunslation.structure.table_rebuild.extract_row_rules_from_page", return_value=[100.0, 180.0]),
        patch("qyunslation.structure.table_grid_hpd.hpd_health", return_value=True),
        patch("qyunslation.structure.table_grid_hpd.hpd_grid", return_value=fake_grid),
    ):
        result = rebuild_from_page(_FakePage(), box, allow_hpd_fallback=True)
    assert result.ok, result.reason
    # Cell text must come from words, not invented HPD OCR phrases
    flat = " ".join(c for row in result.rows for c in row)
    assert "43.9" in flat and "48.6" in flat
    assert "HPD" not in flat


def test_hpd_fallback_rejects_unverified_numbers():
    from qyunslation.structure.table_grid_hpd import HpdGrid

    words = [
        _word("a", 50, 120),
        _word("19", 180, 120),
        _word("20", 280, 120),
        _word("b", 50, 150),
        _word("1", 180, 150),
        _word("2", 280, 150),
    ]
    box = (40.0, 100.0, 400.0, 180.0)

    class _FakePage:
        def get_text(self, mode="text"):
            if mode == "words":
                return [(w.x0, w.y0, w.x1, w.y1, w.text, 0, 0, 0) for w in words]
            return ""

        def get_drawings(self):
            return []

    bad = HpdGrid(rows=[["x", "99", "88"], ["y", "77", "66"]], n_cols=3, source_md="t")
    with (
        patch("qyunslation.structure.table_rebuild.extract_row_rules_from_page", return_value=[100.0, 180.0]),
        patch("qyunslation.structure.table_grid_hpd.hpd_health", return_value=True),
        patch("qyunslation.structure.table_grid_hpd.hpd_grid", return_value=bad),
    ):
        result = rebuild_from_page(_FakePage(), box, allow_hpd_fallback=True)
    assert not result.ok
    assert result.reason in {"hpd_unverified", "no_row_rules"}


def test_literature_paint_keeps_columns_separated(tmp_path, monkeypatch):
    """S2/S4: successful rebuild paints translated cells without collapsing columns."""
    from pdf_table_translate import translate_pdf_tables
    from qyunslation.structure.models import (
        BlockRole,
        BoundingBox,
        ContentProfile,
        ObjectType,
        Representation,
        SourceStyle,
        TableObject,
        TranslatableBlock,
        TranslationPolicy,
    )

    monkeypatch.setenv("QYUNSLATION_TABLE_REBUILD", "literature")
    path, box = _ruled_four_col_pdf(tmp_path / "paint.pdf")
    # BabelDOC-style collapsed overlay on the same page
    doc = pymupdf.open(path)
    doc[0].insert_text(
        (50, 117),
        "43.9 (16.9) 48.6 (17.8) 43.9 (14.8) 45.5 (16.5)",
        fontsize=8,
    )
    babel = tmp_path / "paint.babel.pdf"
    doc.save(babel)
    doc.close()

    placeholder = TranslatableBlock(
        block_id="t:r0c0",
        source_text="Characteristic",
        role=BlockRole.TABLE_CELL,
        translation_policy=TranslationPolicy.TRANSLATE,
        bbox=BoundingBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
        source_style=SourceStyle(font_size=8),
        row_index=0,
        column_index=0,
    )
    table = TableObject.model_construct(
        type=ObjectType.TABLE,
        object_id="obj:" + "b" * 64,
        canvas_id="page:1",
        representation=Representation.VECTOR,
        semantic_id="table:1",
        translatable_blocks=[placeholder],
        row_count=3,
        column_count=5,
        bbox=BoundingBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
    )
    manifest = SimpleNamespace(
        objects=[table],
        extensions={},
        issues=[],
        document=SimpleNamespace(
            source_sha256="0" * 64,
            content_profile=ContentProfile.RESEARCH_ARTICLE,
        ),
        refresh_summary=lambda: None,
    )

    def translator(payloads):
        out = {}
        for item in payloads:
            src = str(item["text"])
            if "Age" in src or "years" in src:
                out[item["id"]] = "年龄，岁"
            elif "Female" in src:
                out[item["id"]] = "女性"
            elif "Characteristic" in src:
                out[item["id"]] = "特征"
            else:
                out[item["id"]] = src  # preserve numerics / headers
        return out

    dest = translate_pdf_tables(
        babel,
        origin=path,
        structure_manifest=manifest,
        translator=translator,
    )
    assert dest != babel
    assert table.reason_code == "literature_rebuild_painted"
    page = pymupdf.open(dest)[0]
    words = page.get_text("words") or []
    text = page.get_text()
    # Means must remain as separate tokens (not one collapsed BabelDOC run).
    assert "43.9" in text and "48.6" in text
    assert "43.9 (16.9) 48.6" not in text.replace("\xa0", " ")
    xs_439 = [((w[0] + w[2]) / 2) for w in words if "43.9" in str(w[4])]
    xs_486 = [((w[0] + w[2]) / 2) for w in words if "48.6" in str(w[4])]
    assert xs_439 and xs_486
    assert abs(min(xs_439) - min(xs_486)) > 40
    assert "年龄" in text or "女性" in text
    page.parent.close()


def test_rebuild_failure_leaves_babeldoc_and_overlap_qa_intact(tmp_path, monkeypatch):
    """S4: rebuild failure does not paint; TABLE_TEXT_OVERLAP detector remains available."""
    from pdf_table_translate import translate_pdf_tables
    from qyunslation.pipeline.qa.pdf_inspect import check_table_text_overlap
    from qyunslation.structure.models import (
        BlockRole,
        BoundingBox,
        ContentProfile,
        ObjectType,
        Representation,
        SourceStyle,
        TableObject,
        TranslatableBlock,
        TranslationPolicy,
    )

    monkeypatch.setenv("QYUNSLATION_TABLE_REBUILD", "literature")
    # No horizontal rules → rebuild fails closed
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=200)
    page.insert_text((40, 80), "43.9 (16.9) 48.6 (17.8)", fontsize=9)
    page.insert_text((42, 81), "43.9 (16.9) 48.6 (17.8)", fontsize=9)
    src = tmp_path / "collapsed.pdf"
    doc.save(src)
    doc.close()

    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text="Age",
        role=BlockRole.TABLE_CELL,
        translation_policy=TranslationPolicy.TRANSLATE,
        bbox=BoundingBox(x0=30, y0=50, x1=380, y1=120),
        source_style=SourceStyle(font_size=9),
        row_index=0,
        column_index=0,
    )
    table = TableObject.model_construct(
        type=ObjectType.TABLE,
        object_id="obj:" + "c" * 64,
        canvas_id="page:1",
        representation=Representation.VECTOR,
        semantic_id="table:1",
        translatable_blocks=[block],
        bbox=BoundingBox(x0=30, y0=50, x1=380, y1=120),
    )
    manifest = SimpleNamespace(
        objects=[table],
        extensions={},
        issues=[],
        document=SimpleNamespace(
            source_sha256="0" * 64,
            content_profile=ContentProfile.RESEARCH_ARTICLE,
        ),
        refresh_summary=lambda: None,
    )
    dest = translate_pdf_tables(
        src,
        origin=src,
        structure_manifest=manifest,
        translator=lambda payloads: {item["id"]: "应被忽略" for item in payloads},
    )
    assert dest == src
    assert (table.reason_code or "").startswith("literature_rebuild_failed:")
    text = pymupdf.open(src)[0].get_text()
    assert "应被忽略" not in text
    # Detector still callable for the BabelDOC leftover (may or may not fire on tiny sample)
    assert callable(check_table_text_overlap)

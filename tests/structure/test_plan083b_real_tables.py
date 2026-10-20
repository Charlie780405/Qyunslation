# SPDX-License-Identifier: MPL-2.0
"""PLAN-083b: three-line literature tables — frame extend + text-line rows."""
from __future__ import annotations

from pathlib import Path

import pytest

from qyunslation.structure.table_rebuild import (
    TableWord,
    extend_frame_to_bottom_rule,
    rebuild_from_page,
    rebuild_literature_table,
    _has_collapsed_value_cells,
)

_SAMPLE = Path(
    "var/pipeline/runs/f3c52a20-cc99-4320-a2b8-6dc7dd303d0c/gen-1/input/"
    "10-LIT-2025-611-Trial.pdf"
)


def _word(text: str, x0: float, y0: float, x1: float | None = None, y1: float | None = None) -> TableWord:
    return TableWord(
        text=text,
        x0=x0,
        y0=y0,
        x1=x0 + (x1 or (6.0 * max(len(text), 1))),
        y1=y0 + (y1 or 10.0),
    )


@pytest.mark.skipif(not _SAMPLE.is_file(), reason="611 sample not present")
def test_real_table1_age_columns_separated():
    import pymupdf

    doc = pymupdf.open(_SAMPLE)
    # Scanner-style header-only box (y 94→123)
    box = (70.9, 94.1, 538.6, 123.5)
    ext, fy = extend_frame_to_bottom_rule(doc[5], box)
    assert fy is not None and abs(fy - 508.7) < 2.0
    assert abs(ext[3] - 508.7) < 2.0
    result = rebuild_from_page(doc[5], box, allow_hpd_fallback=False)
    doc.close()
    assert result.ok, result.reason
    assert result.row_source == "text_lines"
    assert result.n_cols == 5
    assert len(result.rows) >= 15  # header + ≥14 body-ish rows
    age = next(row for row in result.rows if any("43.9" in c for c in row))
    assert age[0].startswith("Age")
    assert "43.9 (16.9)" in age[1] or age[1].startswith("43.9")
    assert "48.6" in age[2]
    assert "45.9" in age[3]
    assert "46.1" in age[4] and "18.3" in age[4]
    # Label column must not absorb numeric means
    assert "43.9" not in age[0]
    assert not any("43.9 (16.9) 48.6" in c for c in age)


@pytest.mark.skipif(not _SAMPLE.is_file(), reason="611 sample not present")
def test_real_table2_treatment_columns_separated():
    import pymupdf

    doc = pymupdf.open(_SAMPLE)
    box = (70.9, 94.1, 538.6, 123.5)
    ext, fy = extend_frame_to_bottom_rule(doc[7], box)
    assert fy is not None and abs(fy - 338.2) < 2.0
    result = rebuild_from_page(doc[7], box, allow_hpd_fallback=False)
    doc.close()
    assert result.ok, result.reason
    assert result.row_source == "text_lines"
    assert result.n_cols == 4
    assert len(result.rows) >= 12  # header + ≥11 data
    teae = next(row for row in result.rows if any("19" in c for c in row))
    assert "19 (63.3)" in teae[1] or teae[1].startswith("19")
    assert "20" in teae[2]
    assert "21" in teae[3]
    assert not any("19 (63.3) 20" in c for c in teae)


def test_three_line_synthetic_splits_by_text_lines():
    """Only three rules (top/header/bottom) — body must split by text lines."""
    rules = [80.0, 110.0, 260.0]
    box = (40.0, 80.0, 500.0, 260.0)
    words = [
        _word("Event", 50, 90),
        _word("A", 200, 90),
        _word("B", 320, 90),
        _word("C", 420, 90),
        _word("Any", 50, 130),
        _word("TEAE", 80, 130),
        _word("19", 200, 130),
        _word("(63.3)", 220, 130),
        _word("20", 320, 130),
        _word("(64.5)", 340, 130),
        _word("21", 420, 130),
        _word("(65.6)", 440, 130),
        _word("Grade", 50, 160),
        _word("3", 90, 160),
        _word("2", 200, 160),
        _word("(6.7)", 220, 160),
        _word("1", 320, 160),
        _word("(3.2)", 340, 160),
        _word("0", 420, 160),
        _word("SAE", 50, 190),
        _word("1", 200, 190),
        _word("(3.3)", 220, 190),
        _word("1", 320, 190),
        _word("(3.2)", 340, 190),
        _word("0", 420, 190),
        # Wrapped Total-style continuation under column C
        _word("(18.3)", 420, 220),
    ]
    # Put a prior Total value so (18.3) merges as continuation
    words.insert(-1, _word("45.5", 420, 205))
    words.insert(-1, _word("Extra", 50, 205))
    result = rebuild_literature_table(words, rules, box=box)
    assert result.ok, result.reason
    assert result.row_source == "text_lines"
    assert len(result.rows) >= 4
    teae = next(row for row in result.rows if any("19" in c for c in row))
    assert len({i for i, c in enumerate(teae) if "19" in c or "20" in c or "21" in c}) >= 3


def test_collapsed_value_groups_rejected():
    assert _has_collapsed_value_cells(
        [
            ["h", "A", "B"],
            ["Age", "43.9 (16.9) 8 (26.7)", "48.6 (17.8)"],
        ]
    )
    assert not _has_collapsed_value_cells(
        [
            ["h", "A", "B"],
            ["Age", "43.9 (16.9)", "48.6 (17.8)"],
        ]
    )


def test_postprocess_summaries_and_dual_hook():
    src = Path("qyunslation/pipeline/stages/postprocess.py").read_text(encoding="utf-8")
    assert "x_min_frac=0.5" in src
    assert "tbltr_dual" in src
    assert "_table_result_summaries" in src
    assert "dual_table_results" in src

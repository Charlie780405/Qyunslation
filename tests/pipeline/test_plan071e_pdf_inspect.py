# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from qyunslation.pipeline.qa.pdf_inspect import (
    check_protected_literals,
    check_translation_text,
    inspect_pdf_pair,
    latin_residue_ratio,
)

SRC = (
    "Contact pind@fda.hhs.gov regarding PIND 123456.\n"
    "Dose 300 mg Q2W; see https://www.fda.gov/drugs.\n"
)


def codes(findings):
    return {f.code: f.severity for f in findings}


def test_missing_email_and_ind_are_blockers():
    found = codes(check_protected_literals(SRC, "请联系 pind@fda.hhs 关于 PIND 12345。"))
    assert found["LITERAL_MISSING_EMAIL"] == "blocker"
    assert found["LITERAL_MISSING_IND"] == "blocker"


def test_preserved_literals_pass():
    zh = "请联系 pind@fda.hhs.gov，PIND 123456。剂量 300 mg Q2W，见 https://www.fda.gov/drugs。"
    assert check_protected_literals(SRC, zh) == []


def test_dose_loss_is_warning_not_blocker():
    found = codes(check_protected_literals(SRC, "请联系 pind@fda.hhs.gov，PIND 123456。剂量 Q2W https://www.fda.gov/drugs"))
    assert found == {"LITERAL_MISSING_DOSE": "warning"}


def test_ordinal_artifact_and_empty_translation():
    assert "ORDINAL_ARTIFACT" in codes(check_translation_text(source_text="5th floor", translated_text="第5^{th}层"))
    assert codes(check_translation_text(source_text="x", translated_text="  ")) == {"EMPTY_TRANSLATION": "blocker"}


def test_untranslated_body_detected():
    english = "\n".join(["The study evaluates the efficacy and safety of the drug in adults"] * 6)
    assert codes(check_translation_text(source_text=english, translated_text=english))["UNTRANSLATED_BODY"] == "blocker"
    assert latin_residue_ratio("这是中文译文\n另一行中文") == 0.0


def test_residue_not_flagged_for_non_chinese_target():
    english = "The study evaluates the efficacy and safety of the drug in adults"
    assert "UNTRANSLATED_BODY" not in codes(
        check_translation_text(source_text=english, translated_text=english, target_is_chinese=False)
    )


pymupdf = pytest.importorskip("pymupdf")


def _pdf(path: Path, lines: list[str], *, pages: int = 1, image: bytes | None = None) -> Path:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        for i, line in enumerate(lines):
            page.insert_text((72, 100 + 20 * i), line, fontname="china-s", fontsize=11)
        if image is not None and _ == 0:
            page.insert_image(pymupdf.Rect(400, 40, 480, 80), stream=image)
    doc.save(str(path))
    return path


def _png(color: int) -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
    pix.set_rect(pix.irect, (color, 40, 90))
    return pix.tobytes("png")


def test_inspect_pair_flags_page_mismatch_and_missing_logo(tmp_path: Path):
    logo = _png(200)
    source = _pdf(tmp_path / "s.pdf", ["Email a@b.com"], pages=2, image=logo)
    mono = _pdf(tmp_path / "m.pdf", ["邮箱 a@b.com"], pages=1, image=_png(10))
    found, summary = inspect_pdf_pair(source_path=source, mono_path=mono, dual_path=None)
    got = codes(found)
    assert got["PAGE_COUNT_MISMATCH"] == "blocker"
    assert got["LOGO_MISSING"] == "blocker"
    assert summary["source_pages"] == 2 and summary["output_pages"] == 1


def test_inspect_pair_clean_translation_has_no_blockers(tmp_path: Path):
    logo = _png(200)
    source = _pdf(tmp_path / "s.pdf", ["Email a@b.com", "Dose 300 mg"], image=logo)
    mono = _pdf(tmp_path / "m.pdf", ["邮箱 a@b.com", "剂量 300 mg"], image=logo)
    found, _ = inspect_pdf_pair(source_path=source, mono_path=mono, dual_path=None)
    assert not [f for f in found if f.severity == "blocker"], found


def test_unreadable_pdf_is_not_silent_pass(tmp_path: Path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF fake")
    source = _pdf(tmp_path / "s.pdf", ["hello"])
    found, summary = inspect_pdf_pair(source_path=source, mono_path=bad, dual_path=None)
    assert codes(found) == {"QA_INPUT_UNAVAILABLE": "warning"}
    assert summary["inputs"] == "unavailable"

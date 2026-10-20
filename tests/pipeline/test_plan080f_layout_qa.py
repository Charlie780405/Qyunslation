# SPDX-License-Identifier: MPL-2.0
"""PLAN-080f：译后 PDF 的段落级漏译、字体种类、装饰线检查（合成 PDF，不含真实文档内容）。"""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from qyunslation.pipeline.qa import pdf_layout as pl
from qyunslation.pipeline.qa.pdf_inspect import inspect_pdf_pair
from qyunslation.pipeline.qa.registry import is_registered, rule_for
from qyunslation.structure import decoration_realign as dr

PARA = (
    "The protocol synopsis does not detail planned subgroup analyses for the primary efficacy endpoint "
    "and the sponsor should pre-specify them before the analysis."
)
ZH = "试验方案摘要未详述主要疗效终点计划的亚组分析，申办方应在分析前预先指定亚组分析。" * 2


def make(path: Path, pages: list[list[tuple[float, str, str]]], lines=None) -> Path:
    """每页是 [(y, 文字, 字体名)]；文字按 80 字符折行，避免超出页宽。"""
    doc = pymupdf.open()
    for number, items in enumerate(pages):
        page = doc.new_page(width=612, height=792)
        for y, text, font in items:
            if any("一" <= c <= "鿿" for c in text):
                page.insert_text((72, y), text[:30], fontname="china-s", fontsize=11)
                continue
            words, row, cur = text.split(), [], y
            for word in words:
                row.append(word)
                if len(" ".join(row)) > 70:
                    page.insert_text((72, cur), " ".join(row), fontname=font, fontsize=11)
                    row, cur = [], cur + 14
            if row:
                page.insert_text((72, cur), " ".join(row), fontname=font, fontsize=11)
        for (x0, x1, y) in (lines or {}).get(number, []):
            page.draw_line((x0, y), (x1, y), color=(0, 0, 1), width=0.8)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv(pl.MODE_ENV, "on")


def codes(findings):
    return {f.code for f in findings}


def test_codes_are_registered_as_warnings():
    for code in ("UNTRANSLATED_PARAGRAPH", "REFERENCE_ENTRIES_CHANGED", "FONT_FAMILY_SPRAWL", "DECORATION_DANGLING"):
        assert is_registered(code)
        assert rule_for(code).rule_class == "W"


def test_mode_defaults_to_off(tmp_path, monkeypatch):
    monkeypatch.delenv(pl.MODE_ENV, raising=False)
    src = make(tmp_path / "s.pdf", [[(100, PARA, "helv")]])
    out = make(tmp_path / "o.pdf", [[(100, PARA, "helv")]])
    assert pl.layout_qa_mode() == "off"
    assert pl.check_output_layout(src, out) == []


def test_verbatim_english_paragraph_is_flagged_with_a_page_anchor(tmp_path):
    src = make(tmp_path / "s.pdf", [[(100, PARA, "helv")]])
    out = make(tmp_path / "o.pdf", [[(100, PARA, "helv")]])
    (finding,) = [f for f in pl.check_output_layout(src, out) if f.code == "UNTRANSLATED_PARAGRAPH"]
    assert finding.severity == "warning"
    assert finding.evidence["count"] == 1 and finding.evidence["pages"] == [1]
    assert finding.location["anchors"][0]["page"] == 1


def test_translated_paragraph_is_not_flagged(tmp_path):
    src = make(tmp_path / "s.pdf", [[(100, PARA, "helv")]])
    out = make(tmp_path / "o.pdf", [[(100, ZH, "helv")]])
    assert "UNTRANSLATED_PARAGRAPH" not in codes(pl.check_output_layout(src, out))


def test_capitalised_lists_and_urls_are_not_flagged(tmp_path):
    texts = [
        "Senior Director of Regulatory Affairs and Clinical Development Operations for Global Programs in Oncology",
        "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/guidance-for-industry-electronic-submissions",
    ]
    src = make(tmp_path / "s.pdf", [[(100, texts[0], "helv"), (200, texts[1], "helv")]])
    out = make(tmp_path / "o.pdf", [[(100, texts[0], "helv"), (200, texts[1], "helv")]])
    assert "UNTRANSLATED_PARAGRAPH" not in codes(pl.check_output_layout(src, out))


def test_reference_list_after_heading_is_not_flagged(tmp_path):
    refs = "2. Smith J, Doe A, and colleagues reported that the treatment effect was consistent across subgroups in the trial."
    page = [(100, "References", "helv"), (130, refs, "helv")]
    src = make(tmp_path / "s.pdf", [page])
    out = make(tmp_path / "o.pdf", [page])
    assert "UNTRANSLATED_PARAGRAPH" not in codes(pl.check_output_layout(src, out))


def test_numbered_body_item_outside_references_is_flagged(tmp_path):
    """旧版 M1 缺陷的形态：编号问题段被整段留成英文，必须能被检出。"""
    item = "2. " + PARA
    src = make(tmp_path / "s.pdf", [[(100, item, "helv")]])
    out = make(tmp_path / "o.pdf", [[(100, item, "helv")]])
    assert "UNTRANSLATED_PARAGRAPH" in codes(pl.check_output_layout(src, out))


def test_running_header_repeated_on_many_pages_is_not_flagged(tmp_path):
    header = "Division of Regulatory Operations for Specialty Medicine and Biosimilar Product Development Review Office"
    pages = [[(40, header, "helv")] for _ in range(4)]
    src = make(tmp_path / "s.pdf", pages)
    out = make(tmp_path / "o.pdf", pages)
    assert "UNTRANSLATED_PARAGRAPH" not in codes(pl.check_output_layout(src, out))


FONTS = ["helv", "hebo", "heit", "tiro", "tibo", "tiit", "cour", "cobo"]


def test_font_sprawl_is_flagged_only_when_it_exceeds_the_source(tmp_path):
    many = [[(60 + 40 * i, "alpha beta gamma delta epsilon zeta eta theta", font) for i, font in enumerate(FONTS)]]
    one = [[(100, "alpha beta gamma delta epsilon zeta eta theta", "helv")]]
    src = make(tmp_path / "s.pdf", one)
    out = make(tmp_path / "o.pdf", many)
    (finding,) = [f for f in pl.check_output_layout(src, out) if f.code == "FONT_FAMILY_SPRAWL"]
    assert finding.evidence["max_families"] >= 7
    # 源文本来就用这么多种字体：不是翻译造成的，不标记
    assert "FONT_FAMILY_SPRAWL" not in codes(pl.check_output_layout(make(tmp_path / "s2.pdf", many), out))


def test_dangling_decoration_is_flagged_until_it_is_realigned(tmp_path):
    long = "Draft Guidance for Industry on Combination Product Risk Analysis"
    width = pymupdf.get_text_length(long, fontname="helv", fontsize=11)
    src = make(tmp_path / "s.pdf", [[(100, long, "helv")]], lines={0: [(72, 72 + width, 102.0)]})
    out = make(tmp_path / "o.pdf", [[(100, "产品风险分析指南", "helv")]], lines={0: [(72, 72 + width, 102.0)]})
    assert "DECORATION_DANGLING" in codes(pl.check_output_layout(src, out))
    dr.realign_pdf(src, out, tmp_path / "fixed.pdf")
    assert "DECORATION_DANGLING" not in codes(pl.check_output_layout(src, tmp_path / "fixed.pdf"))


def test_unreadable_output_returns_no_findings(tmp_path):
    src = make(tmp_path / "s.pdf", [[(100, PARA, "helv")]])
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    assert pl.check_output_layout(src, bad) == []


def test_inspect_pdf_pair_includes_the_layout_findings(tmp_path, monkeypatch):
    src = make(tmp_path / "s.pdf", [[(100, PARA, "helv")]])
    mono = make(tmp_path / "m.pdf", [[(100, PARA, "helv")]])
    findings, _summary = inspect_pdf_pair(source_path=src, mono_path=mono, dual_path=None)
    assert "UNTRANSLATED_PARAGRAPH" in codes(findings)
    monkeypatch.setenv(pl.MODE_ENV, "off")
    findings, _summary = inspect_pdf_pair(source_path=src, mono_path=mono, dual_path=None)
    assert "UNTRANSLATED_PARAGRAPH" not in codes(findings)


def test_page_count_mismatch_only_runs_the_pairing_free_check(tmp_path):
    """页数对不上时字体与装饰线的配对不可靠；漏译检查不依赖配对，仍然运行。"""
    long = "Draft Guidance for Industry on Combination Product Risk Analysis"
    width = pymupdf.get_text_length(long, fontname="helv", fontsize=11)
    src = make(tmp_path / "s.pdf", [[(100, long, "helv")]], lines={0: [(72, 72 + width, 102.0)]})
    out = make(
        tmp_path / "o.pdf",
        [[(100, "产品风险分析指南", "helv")], [(100, PARA, "helv")]],
        lines={0: [(72, 72 + width, 102.0)]},
    )
    found = codes(pl.check_output_layout(src, out))
    assert "DECORATION_DANGLING" not in found and "FONT_FAMILY_SPRAWL" not in found
    assert "UNTRANSLATED_PARAGRAPH" in found


REFERENCE = (
    "1. Smith J, Doe A, Lee K. Efficacy of drug X in atopic dermatitis. J Allergy Clin Immunol. 2024;153(2):345-52. "
    "doi:10.1016/j.jaci.2023.10.001"
)


def make_blocks(path: Path, pages: list[str]) -> Path:
    """每页一个文本框（真实的段落是一个文本块，而不是逐行独立的文本）。"""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page(width=612, height=792)
        font = "china-s" if any("\u4e00" <= c <= "\u9fff" for c in text) else "helv"
        page.insert_textbox(pymupdf.Rect(72, 80, 540, 300), text, fontname=font, fontsize=11)
    doc.save(path)
    doc.close()
    return path


def test_translated_reference_is_flagged_and_verbatim_reference_is_not(tmp_path):
    src = make_blocks(tmp_path / "s.pdf", [REFERENCE])
    kept = make_blocks(tmp_path / "k.pdf", [REFERENCE])
    changed = make_blocks(tmp_path / "c.pdf", [ZH])
    assert "REFERENCE_ENTRIES_CHANGED" not in codes(pl.check_output_layout(src, kept))
    (finding,) = [f for f in pl.check_output_layout(src, changed) if f.code == "REFERENCE_ENTRIES_CHANGED"]
    assert finding.severity == "warning" and finding.evidence["pages"] == [1]


def test_reference_check_needs_the_same_page_count(tmp_path):
    src = make_blocks(tmp_path / "s.pdf", [REFERENCE])
    out = make_blocks(tmp_path / "o.pdf", [ZH, ZH])
    assert "REFERENCE_ENTRIES_CHANGED" not in codes(pl.check_output_layout(src, out))

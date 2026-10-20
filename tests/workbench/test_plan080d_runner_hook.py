# SPDX-License-Identifier: MPL-2.0
"""PLAN-080d：runner 的装饰线后处理钩子——默认关闭，开启后原地处理，失败不影响交付。"""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure import decoration_realign as dr
from qyunslation.workbench.runner import Pdf2zhRunner

LONG = "Draft Guidance for Industry on Combination Product Risk Analysis"
SHORT = "Guidance on Product Risk Analysis"


def _pdf(path: Path, text: str, line_to: float) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), text, fontname="helv", fontsize=12)
    page.draw_line((72, 102), (line_to, 102), color=(0, 0, 1), width=0.8)
    doc.save(path)
    doc.close()
    return path


def _line_end(path: Path) -> float:
    doc = pymupdf.open(path)
    try:
        return max(seg.x1 for seg in dr._thin_segments(doc[0]))
    finally:
        doc.close()


def _setup(tmp_path: Path):
    width = pymupdf.get_text_length(LONG, fontname="helv", fontsize=12)
    source = _pdf(tmp_path / "source.pdf", LONG, 72 + width)
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    out = _pdf(out_dir / "doc.zh.mono.pdf", SHORT, 72 + width)
    return source, out_dir, out, 72 + width


def test_hook_is_a_no_op_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv(dr.MODE_ENV, raising=False)
    source, out_dir, out, original_end = _setup(tmp_path)
    assert Pdf2zhRunner._realign_decorations(source, out_dir) is None
    assert _line_end(out) == pytest.approx(original_end, abs=0.01)


def test_hook_trims_the_line_in_place_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv(dr.MODE_ENV, "on")
    source, out_dir, out, original_end = _setup(tmp_path)
    summary = Pdf2zhRunner._realign_decorations(source, out_dir)
    assert summary["doc.zh.mono.pdf"]["trimmed"] == 1
    assert _line_end(out) < original_end - 50
    assert list(out_dir.glob(".*")) == []  # 没有残留的临时文件


def test_hook_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv(dr.MODE_ENV, "on")
    source, out_dir, out, _ = _setup(tmp_path)
    out.write_bytes(b"not a pdf")  # 损坏的产物
    summary = Pdf2zhRunner._realign_decorations(source, out_dir)
    assert "error" in summary["doc.zh.mono.pdf"]
    assert out.read_bytes() == b"not a pdf"
    # 源文件缺失同样静默跳过
    assert Pdf2zhRunner._realign_decorations(tmp_path / "missing.pdf", out_dir) is None

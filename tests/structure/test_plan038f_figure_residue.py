# SPDX-License-Identifier: MPL-2.0
"""PLAN-038f：Figure 残影探针单测。"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_probe():
    path = Path(__file__).resolve().parents[2] / "scripts" / "probe-figure-ink-residue.py"
    spec = importlib.util.spec_from_file_location("probe_figure_ink_residue", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _twin_pdfs(tmp_path: Path):
    import pymupdf

    src = tmp_path / "src.pdf"
    dst_ok = tmp_path / "dst-ok.pdf"
    dst_bad = tmp_path / "dst-bad.pdf"

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    page.draw_rect(pymupdf.Rect(40, 40, 160, 160), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(src)
    doc.close()

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    # 白底擦除 → 原文墨迹不该残留
    page.draw_rect(pymupdf.Rect(40, 40, 160, 160), color=(1, 1, 1), fill=(1, 1, 1))
    doc.save(dst_ok)
    doc.close()

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    page.draw_rect(pymupdf.Rect(40, 40, 160, 160), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(dst_bad)
    doc.close()
    return src, dst_ok, dst_bad


def test_probe_figure_residue_ok_and_warn(tmp_path: Path):
    mod = _load_probe()
    src, dst_ok, dst_bad = _twin_pdfs(tmp_path)
    ok = mod.probe_figure_residue(src, dst_ok, bbox=(40, 40, 160, 160), residue_frac_warn=0.08)
    bad = mod.probe_figure_residue(src, dst_bad, bbox=(40, 40, 160, 160), residue_frac_warn=0.08)
    assert ok["status"] == "ok"
    assert bad["status"] == "warn"
    assert bad["residue_frac"] >= 0.08

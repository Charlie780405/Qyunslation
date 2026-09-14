# SPDX-License-Identifier: MPL-2.0
"""PLAN-052a：promote 夹具（不入库 PDF）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qyunslation.gold.plan052_promote import (
    Plan052PromoteError,
    assert_kind_allowed,
    product_ready,
    promote_entry,
)


def _mini_catalog(tmp: Path) -> Path:
    """一条 synthetic R + 凑齐 L/C 各 10 太重；assert 可 skip，或造最小完备集。"""
    # 为 assert_catalog_complete：三类各 ≥10 ready — 太重。
    # 单测用 skip_assert=True，另测类诚实性与 tags。
    cat = {
        "schema_version": "1.0.0",
        "plan": "PLAN-052-test",
        "entries": [
            {
                "id": "R-01",
                "class": "R",
                "title": "CTD placeholder",
                "format": "pdf",
                "lang_pair": "en→zh",
                "sha256": "0" * 64,
                "relpath": "R-01.pdf",
                "tags": ["synthetic", "synthetic-slot", "ctd-m2"],
                "status": "ready",
            },
            {
                "id": "C-04",
                "class": "C",
                "title": "Protocol placeholder",
                "format": "pdf",
                "lang_pair": "en→zh",
                "sha256": "1" * 64,
                "relpath": "C-04.pdf",
                "tags": ["synthetic", "synthetic-slot"],
                "status": "ready",
            },
        ],
    }
    path = tmp / "catalog.json"
    path.write_text(json.dumps(cat, indent=2), encoding="utf-8")
    return path


def test_assert_kind_r_rejects_protocol():
    with pytest.raises(Plan052PromoteError):
        assert_kind_allowed("R", "protocol")
    assert_kind_allowed("R", "ctd-m2")
    assert_kind_allowed("C", "protocol")
    assert_kind_allowed("C", "cdp")
    with pytest.raises(Plan052PromoteError):
        assert_kind_allowed("R", "cdp")


def test_promote_synthetic_to_real(tmp_path: Path):
    gold = tmp_path / "gold"
    cat = _mini_catalog(tmp_path)
    src = tmp_path / "real-ctd.pdf"
    # 非占位：写不同内容
    src.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n" + b"x" * 200)

    out = promote_entry(
        "R-01",
        src=src,
        kind="ctd-m2",
        extra_tags=["ctd-m2"],
        gold_root_path=gold,
        catalog=cat,
        skip_assert=True,
    )
    assert out["tags"][0] == "real"
    assert "synthetic" not in out["tags"]
    dest = Path(out["dest"])
    assert dest.is_symlink() or dest.is_file()
    raw = json.loads(cat.read_text(encoding="utf-8"))
    row = next(e for e in raw["entries"] if e["id"] == "R-01")
    assert "real" in row["tags"]
    assert "synthetic" not in row["tags"]
    assert row["sha256"] == out["sha256"]


def test_refuse_protocol_into_r(tmp_path: Path):
    gold = tmp_path / "gold"
    cat = _mini_catalog(tmp_path)
    src = tmp_path / "proto.pdf"
    src.write_bytes(b"%PDF-1.4 protocol fake\n%%EOF\n")
    with pytest.raises(Plan052PromoteError, match="not allowed"):
        promote_entry(
            "R-01",
            src=src,
            kind="protocol",
            gold_root_path=gold,
            catalog=cat,
            skip_assert=True,
        )


def test_promote_c_protocol(tmp_path: Path):
    gold = tmp_path / "gold"
    cat = _mini_catalog(tmp_path)
    src = tmp_path / "STREAM.pdf"
    src.write_bytes(b"%PDF-1.4 STREAM-AD\n%%EOF\n" + b"y" * 100)
    out = promote_entry(
        "C-04",
        src=src,
        kind="protocol",
        extra_tags=["protocol"],
        gold_root_path=gold,
        catalog=cat,
        skip_assert=True,
    )
    assert "protocol" in out["tags"]
    assert out["class"] == "C"


def test_product_ready_helper():
    assert product_ready({"L": 1, "C": 1, "R": 1, "total": 3}) is True
    assert product_ready({"L": 6, "C": 3, "R": 0, "total": 9}) is False


def test_gs101_registry_roles():
    """方案/CDP→C；M2.5 综述→R。"""
    from qyunslation.gold.plan052_promote import load_real_sources

    by = {e["entry_id"]: e for e in load_real_sources()["entries"]}
    assert by["C-06"]["class"] == "C" and by["C-06"]["kind"] == "protocol"
    assert "方案" in by["C-06"]["windows_hint"] or "Protocol" in by["C-06"]["inbox_name"]
    assert by["C-07"]["class"] == "C" and by["C-07"]["kind"] == "cdp"
    assert "开发计划" in by["C-07"]["windows_hint"] or "CDP" in by["C-07"]["inbox_name"]
    assert by["R-01"]["class"] == "R" and by["R-01"]["kind"] == "ctd-m2"
    assert "综述" in by["R-01"]["windows_hint"] or "Overview" in by["R-01"]["inbox_name"]


def test_promote_cdp_to_c_not_r(tmp_path: Path):
    gold = tmp_path / "gold"
    cat = _mini_catalog(tmp_path)
    src = tmp_path / "cdp.pdf"
    src.write_bytes(b"%PDF-1.4 CDP\n%%EOF\n" + b"z" * 80)
    # mini catalog 无 C-07，用 C-04 槽测 kind=cdp
    out = promote_entry(
        "C-04",
        src=src,
        kind="cdp",
        extra_tags=["cdp"],
        gold_root_path=gold,
        catalog=cat,
        skip_assert=True,
    )
    assert out["class"] == "C"
    with pytest.raises(Plan052PromoteError, match="not allowed"):
        promote_entry(
            "R-01",
            src=src,
            kind="cdp",
            gold_root_path=gold,
            catalog=cat,
            skip_assert=True,
        )


def test_ensure_pdf_passthrough(tmp_path: Path):
    from qyunslation.gold.plan052_promote import ensure_pdf_source

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    assert ensure_pdf_source(pdf, work_dir=tmp_path / "w") == pdf


def test_ensure_pdf_rejects_unknown(tmp_path: Path):
    from qyunslation.gold.plan052_promote import Plan052PromoteError, ensure_pdf_source

    bad = tmp_path / "x.txt"
    bad.write_text("nope", encoding="utf-8")
    with pytest.raises(Plan052PromoteError, match="unsupported"):
        ensure_pdf_source(bad, work_dir=tmp_path / "w")

# SPDX-License-Identifier: MPL-2.0
"""PLAN-051a：runner 缓存与选条目（mock CLI，不烧 GPU）。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from qyunslation.gold.plan034 import GoldEntry
from qyunslation.gold.plan051_run import (
    Plan051Blocked,
    is_cache_hit,
    run_one,
    select_entries,
)


def _entry(
    eid: str = "L-test",
    *,
    sha: str = "a" * 64,
    tags: tuple[str, ...] = ("real",),
) -> GoldEntry:
    return GoldEntry(
        id=eid,
        class_="L",
        title="t",
        format="pdf",
        lang_pair="en→zh",
        sha256=sha,
        relpath=f"{eid}.pdf",
        tags=tags,
        status="ready",
    )


def test_drop_scanned_original_when_ocr_sibling():
    from qyunslation.gold.plan051_run import drop_scanned_originals, select_entries

    scan = _entry("C-fda-pind", tags=("real", "pind"))
    ocr = _entry("C-fda-pind-ocr", tags=("real", "pind", "ocr"))
    proto = _entry("C-04", tags=("real", "protocol"))
    got = drop_scanned_originals([scan, ocr, proto])
    assert [e.id for e in got] == ["C-fda-pind-ocr", "C-04"]
    got2 = select_entries([scan, ocr, proto], include_synthetic=False)
    assert [e.id for e in got2] == ["C-fda-pind-ocr", "C-04"]
    # 显式 --entry 仍可选原件
    got3 = select_entries([scan, ocr], include_synthetic=False, entry_id="C-fda-pind")
    assert [e.id for e in got3] == ["C-fda-pind"]


def test_select_entries_real_only():
    items = [
        _entry("r1", tags=("real",)),
        _entry("s1", tags=("synthetic",)),
        _entry("p1", tags=("real",)),
    ]
    # pending-like: status ready already; synthetic excluded
    got = select_entries(items, include_synthetic=False)
    assert [e.id for e in got] == ["r1", "p1"]
    got2 = select_entries(items, include_synthetic=True)
    assert [e.id for e in got2] == ["r1", "s1", "p1"]
    got3 = select_entries(items, include_synthetic=True, limit=1)
    assert [e.id for e in got3] == ["r1"]


def test_cache_hit_skips_second_translate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src_root = tmp_path / "gold"
    src_dir = src_root / "L"
    src_dir.mkdir(parents=True)
    pdf = src_dir / "L-test.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    import hashlib

    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    entry = _entry(sha=sha)

    calls: list[str] = []

    def fake_translate(e, src, out_dir):
        calls.append(e.id)
        out_dir.mkdir(parents=True, exist_ok=True)
        mono = out_dir / "L-test.mono.pdf"
        mono.write_bytes(b"%PDF mono")
        return {
            "mono": str(mono),
            "dual": "",
            "sidecar": [],
            "exit_code": 0,
            "model_id": "mock",
        }

    out = tmp_path / "out"
    r1 = run_one(
        entry,
        out_root=out,
        gold_root_path=src_root,
        translate_fn=fake_translate,
    )
    assert r1["cached"] is False
    assert is_cache_hit(entry, out_root=out)
    r2 = run_one(
        entry,
        out_root=out,
        gold_root_path=src_root,
        translate_fn=fake_translate,
    )
    assert r2["cached"] is True
    assert calls == ["L-test"]


def test_hash_change_reruns(tmp_path: Path):
    src_root = tmp_path / "gold"
    src_dir = src_root / "L"
    src_dir.mkdir(parents=True)
    pdf = src_dir / "L-test.pdf"
    pdf.write_bytes(b"%PDF-1.4 v1")
    import hashlib

    sha1 = hashlib.sha256(pdf.read_bytes()).hexdigest()
    entry1 = _entry(sha=sha1)
    out = tmp_path / "out"
    n = {"i": 0}

    def fake_translate(e, src, out_dir):
        n["i"] += 1
        out_dir.mkdir(parents=True, exist_ok=True)
        mono = out_dir / f"mono-{n['i']}.pdf"
        mono.write_bytes(b"%PDF mono")
        return {"mono": str(mono), "dual": "", "sidecar": [], "exit_code": 0, "model_id": "m"}

    run_one(entry1, out_root=out, gold_root_path=src_root, translate_fn=fake_translate)
    pdf.write_bytes(b"%PDF-1.4 v2-changed")
    sha2 = hashlib.sha256(pdf.read_bytes()).hexdigest()
    entry2 = _entry(sha=sha2)
    run_one(entry2, out_root=out, gold_root_path=src_root, translate_fn=fake_translate)
    assert n["i"] == 2


def test_missing_source_blocked(tmp_path: Path):
    entry = _entry()
    with pytest.raises(Plan051Blocked):
        run_one(entry, out_root=tmp_path / "out", gold_root_path=tmp_path / "empty")


def test_build_tmp_config_skip_scanned(tmp_path: Path):
    from qyunslation.gold.plan051_run import build_tmp_config

    src = tmp_path / "in.toml"
    src.write_text("gui = true\nskip_scanned_detection = false\n", encoding="utf-8")
    dest = build_tmp_config(out_dir=tmp_path / "o", config_src=src, skip_scanned=True)
    text = dest.read_text(encoding="utf-8")
    assert "skip_scanned_detection = true" in text
    assert "gui = false" in text


def test_pdf2zh_subprocess_env_prepends_repo():
    from qyunslation.gold.plan051_run import _repo_root, pdf2zh_subprocess_env

    root = str(_repo_root())
    env = pdf2zh_subprocess_env({"PATH": "/bin", "PYTHONPATH": "/other"})
    assert env["PYTHONPATH"].split(os.pathsep)[0] == root
    assert "/other" in env["PYTHONPATH"]

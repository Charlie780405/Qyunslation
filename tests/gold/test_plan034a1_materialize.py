# SPDX-License-Identifier: MPL-2.0
"""PLAN-034a1 materialize + synthetic hash stability."""
from __future__ import annotations

from pathlib import Path

import pytest

from qyunslation.gold.plan034 import assert_catalog_complete, load_catalog
from qyunslation.gold.synthesize import write_placeholder_pdf


def test_synthetic_pdf_hash_stable(tmp_path: Path):
    p1 = tmp_path / "a.pdf"
    p2 = tmp_path / "b.pdf"
    h1 = write_placeholder_pdf(
        p1, gold_class="L", entry_id="L-07", title="Literature gold placeholder 7"
    )
    h2 = write_placeholder_pdf(
        p2, gold_class="L", entry_id="L-07", title="Literature gold placeholder 7"
    )
    assert h1 == h2
    assert p1.read_bytes() == p2.read_bytes()
    assert len(h1) == 64


def test_materialize_tmp_gold_complete(tmp_path: Path):
    import subprocess
    import sys

    gold = tmp_path / "gold"
    catalog = tmp_path / "catalog.json"
    script = Path(__file__).resolve().parents[2] / "scripts" / "plan034a-materialize-gold.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--gold-root",
            str(gold),
            "--catalog",
            str(catalog),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    loaded = load_catalog(catalog)
    summary = assert_catalog_complete(loaded, root=gold)
    assert summary["ready_total"] == 30
    assert summary["per_class"] == {"L": 10, "C": 10, "R": 10}


def test_repo_catalog_ready_tags():
    entries = load_catalog()
    by = {"L": 0, "C": 0, "R": 0}
    for e in entries:
        if e.status != "ready":
            continue
        by[e.class_] += 1
        has_real = "real" in e.tags
        has_synth = "synthetic" in e.tags
        assert has_real ^ has_synth, e.id
    assert by["L"] >= 10 and by["C"] >= 10 and by["R"] >= 10

# SPDX-License-Identifier: MPL-2.0
"""PLAN-034a catalog / thresholds / hash fixtures."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qyunslation.gold.plan034 import (
    CatalogCompletenessError,
    assert_catalog_complete,
    evaluate_baseline_report,
    load_catalog,
    load_thresholds,
    resolve_entry,
    verify_entry_hash,
)


def test_load_repo_catalog_schema():
    entries = load_catalog()
    assert len(entries) >= 30
    classes = {e.class_ for e in entries}
    assert classes == {"L", "C", "R"}
    by = {"L": 0, "C": 0, "R": 0}
    for e in entries:
        by[e.class_] += 1
        assert e.id
        assert len(e.sha256) == 64
    assert by["L"] >= 10 and by["C"] >= 10 and by["R"] >= 10


def test_load_thresholds():
    th = load_thresholds()
    assert th["version"] == "1.0.0"
    assert th["critical_max"] == 0
    assert th["hard_term_hit_min"] == 0.98
    assert th["forbidden_translation_max"] == 0
    assert th["digit_unit_doi_ref_pass"] == 1.0


def test_evaluate_baseline_report_pass_fail():
    th = load_thresholds()
    ok = {
        "critical_count": 0,
        "hard_term_hit_rate": 0.99,
        "forbidden_translation_count": 0,
        "digit_unit_doi_ref_pass_rate": 1.0,
    }
    assert evaluate_baseline_report(ok, th) == "pass"
    bad = dict(ok)
    bad["critical_count"] = 1
    assert evaluate_baseline_report(bad, th) == "fail"
    bad2 = dict(ok)
    bad2["hard_term_hit_rate"] = 0.5
    assert evaluate_baseline_report(bad2, th) == "fail"


def test_verify_entry_hash_roundtrip(tmp_path):
    blob = b"plan034a-fixture-bytes"
    path = tmp_path / "L" / "x.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    from qyunslation.gold.plan034 import GoldEntry

    entry = GoldEntry(
        id="L-fix",
        class_="L",
        title="t",
        format="pdf",
        lang_pair="en→zh",
        sha256=digest,
        relpath="x.pdf",
        status="ready",
    )
    assert resolve_entry(entry, tmp_path) == path
    assert verify_entry_hash(entry, path)


def test_assert_catalog_complete_blocked_on_empty_root(tmp_path):
    entries = load_catalog()
    with pytest.raises(CatalogCompletenessError) as ei:
        assert_catalog_complete(entries, root=tmp_path, min_per_class=10)
    msg = str(ei.value)
    assert "class L" in msg or "class C" in msg or "missing" in msg


def test_catalog_json_roundtrip_counts():
    raw = json.loads(
        Path("docs/gold/plan034/catalog.json").read_text(encoding="utf-8")
    )
    assert raw["schema_version"] == "1.0.0"
    assert len(raw["entries"]) == 30

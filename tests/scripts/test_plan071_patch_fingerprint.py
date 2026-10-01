# SPDX-License-Identifier: MPL-2.0
"""PLAN-071a：补丁指纹脚本契约测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import plan071_patch_fingerprint as fp  # noqa: E402


def test_known_patches_non_empty_and_unique():
    ids = [p[0] for p in fp.KNOWN_PATCHES]
    assert len(ids) >= 10
    assert len(ids) == len(set(ids))


def test_markers_aligned_with_apply_scripts_when_declared():
    declared = fp.markers_from_apply_scripts()
    # Every apply_script referenced in KNOWN_PATCHES must exist on disk.
    for _pid, script, marker, _hint in fp.KNOWN_PATCHES:
        path = SCRIPTS / script
        assert path.is_file(), script
        text = path.read_text(encoding="utf-8", errors="replace")
        assert marker in text, f"{script} missing marker {marker!r}"
        # If the script declares MARKER constants, at least one should appear in registry
        if script in declared:
            assert declared[script], script


def test_build_report_without_site(tmp_path: Path):
    missing = tmp_path / "no-site"
    report = fp.build_report(missing)
    assert report["schema"] == "plan071-patch-fingerprint/v1"
    assert report["site_exists"] is False
    assert report["present_count"] == 0
    assert report["missing_count"] == len(fp.KNOWN_PATCHES)
    assert len(report["fingerprint_sha256"]) == 64


def test_detect_marker_in_fake_gui(tmp_path: Path):
    site = tmp_path / "site-packages"
    gui = site / "pdf2zh_next" / "gui.py"
    gui.parent.mkdir(parents=True)
    gui.write_text(
        "# fake\ndef _qy_imgtr_post():\n    pass\n_qy_tbltr = True\n",
        encoding="utf-8",
    )
    report = fp.build_report(site)
    by_id = {p["patch_id"]: p for p in report["patches"]}
    assert by_id["docimg-imgtr"]["present"] is True
    assert by_id["docimg-tbltr"]["present"] is True
    assert by_id["047c"]["present"] is False


def test_cli_writes_out(tmp_path: Path):
    out = tmp_path / "fp.json"
    code = fp.main(["--site", str(tmp_path / "absent"), "-o", str(out)])
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["known_patch_count"] == len(fp.KNOWN_PATCHES)


def test_cli_fail_if_missing_site(tmp_path: Path):
    code = fp.main(["--site", str(tmp_path / "absent"), "--fail-if-missing-site"])
    assert code == 2

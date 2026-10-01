# SPDX-License-Identifier: MPL-2.0
"""PLAN-071b：原件只读封印。"""
from __future__ import annotations

import stat
from pathlib import Path

import pytest

from qyunslation.pipeline.workspace import RunWorkspace


def test_seal_source_is_readonly_and_stable(tmp_path: Path):
    ws = RunWorkspace(tmp_path / "ws")
    source = tmp_path / "in.pdf"
    source.write_bytes(b"%PDF-1.7 sealed")
    before_mtime = source.stat().st_mtime_ns
    sealed = ws.seal_source(source)
    assert sealed.sha256 == ws.sha256_file(source)
    mode = sealed.path.stat().st_mode
    assert not (mode & stat.S_IWUSR)
    work = ws.materialize_work_copy(
        sealed, run_id="run-1", generation=1, filename="in.pdf"
    )
    work.write_bytes(b"%PDF-1.7 mutated work copy")
    ws.assert_source_unchanged(sealed)
    assert source.stat().st_mtime_ns == before_mtime
    assert ws.sha256_file(source) == sealed.sha256


def test_work_copy_does_not_alias_sealed_path(tmp_path: Path):
    ws = RunWorkspace(tmp_path / "ws")
    source = tmp_path / "doc.docx"
    source.write_bytes(b"PK\x03\x04fake")
    sealed = ws.seal_source(source, suffix=".docx")
    work = ws.materialize_work_copy(
        sealed, run_id="run-2", generation=1, filename="doc.docx"
    )
    assert work.resolve() != sealed.path.resolve()

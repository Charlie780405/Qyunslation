# SPDX-License-Identifier: MPL-2.0
"""PLAN-071b：DocumentPipeline 骨架与 CLI 非正式终态。"""
from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path

import pytest

from qyunslation.pipeline import DocumentPipeline, pipeline_mode
from qyunslation.pipeline.workspace import RunWorkspace
from qyunslation.workbench.runner import Pdf2zhRunner


def _fake_cli(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import pathlib, sys
args = sys.argv[1:]
out = pathlib.Path(args[args.index('--output') + 1])
out.mkdir(parents=True, exist_ok=True)
src = pathlib.Path(args[-1])
(out / (src.stem + '_dual.pdf')).write_bytes(b'%PDF fake output')
print('Progress: 1.0, export', flush=True)
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_pipeline_mode_defaults_legacy(monkeypatch):
    monkeypatch.delenv("QYUNSLATION_PIPELINE", raising=False)
    assert pipeline_mode() == "legacy"
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "v2")
    assert pipeline_mode() == "v2"


@pytest.mark.asyncio
async def test_v2_cli_success_is_layout_complete_not_succeeded(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "v2")
    cli = tmp_path / "fake-pdf2zh"
    _fake_cli(cli)
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CLI", str(cli))
    config = tmp_path / "config.toml"
    config.write_text("[basic]\ngui = true\n", encoding="utf-8")
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CONFIG", str(config))

    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7 text layer")
    runner = Pdf2zhRunner(tmp_path / "runs")
    pipeline = DocumentPipeline(
        workspace=RunWorkspace(tmp_path / "pipeline"),
        pdf_executor=__import__(
            "qyunslation.pipeline.executors", fromlist=["PdfCliExecutor"]
        ).PdfCliExecutor(runner),
    )
    launch = await pipeline.start(
        tenant_id="tenant-1",
        run_id="run-v2",
        generation=1,
        source_path=source,
        source_format="pdf",
        original_filename="source.pdf",
        direction="English → 简体中文",
        target_language="简体中文",
        scanned_hint=False,
    )
    assert launch.manifest_version.startswith("2.")
    assert any(e["stage"] == "ocr" and e["state"] == "skipped" for e in launch.events)

    state = None
    for _ in range(40):
        state = runner.read_task_state(launch.external_task_id)
        if state and state["status"] in {"layout_complete", "failed", "succeeded"}:
            break
        await asyncio.sleep(0.05)
    assert state is not None
    assert state["status"] == "layout_complete"
    assert state["stage"] == "layout"
    assert state["progress_percent"] is None
    assert state["download_ready"] is False
    assert state["cli_complete"] is True
    assert state["status"] != "succeeded"


@pytest.mark.asyncio
async def test_legacy_cli_success_still_succeeded(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "legacy")
    cli = tmp_path / "fake-pdf2zh"
    _fake_cli(cli)
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CLI", str(cli))
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7")
    runner = Pdf2zhRunner(tmp_path / "runs")
    launch = await runner.start(
        tenant_id="tenant-1",
        run_id="run-legacy",
        generation=1,
        input_path=source,
        direction="English → 简体中文",
        original_filename="source.pdf",
    )
    state = None
    for _ in range(40):
        state = runner.read_task_state(launch.task_id)
        if state and state["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.05)
    assert state is not None
    assert state["status"] == "succeeded"
    assert state["download_ready"] is True

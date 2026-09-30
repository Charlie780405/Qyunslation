from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path

import pytest

from qyunslation.workbench.runner import (
    Pdf2zhRunner,
    _progress_message_from_line,
    build_pdf2zh_command,
)


def _fake_cli(path: Path, *, delay: float = 0.0) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import pathlib, sys, time
args = sys.argv[1:]
out = pathlib.Path(args[args.index('--output') + 1])
out.mkdir(parents=True, exist_ok=True)
print('Progress: 0.25, parse document', flush=True)
time.sleep(DELAY)
print('Progress: 0.75, translate text', flush=True)
time.sleep(DELAY)
src = pathlib.Path(args[-1])
(out / (src.stem + '_dual.pdf')).write_bytes(b'%PDF fake output')
print('Progress: 1.0, export', flush=True)
""".replace("DELAY", repr(delay)),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fake_scan_then_ocr_cli(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import pathlib, sys
args = sys.argv[1:]
out = pathlib.Path(args[args.index('--output') + 1])
src = pathlib.Path(args[-1])
if not src.name.endswith('.hpd-ocr.pdf'):
    print('Progress: 1.0, scan failed without output', flush=True)
    raise SystemExit(0)
out.mkdir(parents=True, exist_ok=True)
(out / (src.stem + '_dual.pdf')).write_bytes(b'%PDF fake OCR output')
print('Progress: 1.0, export', flush=True)
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_pdf2zh_command_uses_cli_flags_without_credentials(tmp_path: Path):
    command = build_pdf2zh_command(
        executable="pdf2zh_next",
        input_path=tmp_path / "source.pdf",
        output_dir=tmp_path / "out",
        direction="English → 简体中文",
        settings={"pages": "1-2", "api_key": "do-not-copy"},
    )
    assert command[-1].endswith("source.pdf")
    assert "--lang-in" in command and command[command.index("--lang-in") + 1] == "en"
    assert "--auto-enable-ocr-workaround" in command
    assert "do-not-copy" not in command
    assert "--api-key" not in command


def test_pdf_runner_env_exposes_package_parent_to_cli_workers():
    import qyunslation.workbench.runner as runner_module

    env = runner_module._runner_env()
    package_parent = str(Path(runner_module.__file__).resolve().parents[3])
    assert package_parent in env["PYTHONPATH"].split(os.pathsep)


def test_runner_extracts_human_readable_live_progress_from_cli_output():
    assert _progress_message_from_line(
        "Translate Paragraphs (1/1) ━━━━━ 126/… 0:00:… 0:00:…"
    ) == "正在翻译段落"
    assert _progress_message_from_line(
        "Typesetting (1/1) ━━━━━ 18/18 0:00:… 0:00:…"
    ) == "正在处理版式"
    assert _progress_message_from_line("INFO: unrelated diagnostic") is None


@pytest.mark.asyncio
async def test_runner_writes_atomic_state_and_discovers_outputs(tmp_path: Path, monkeypatch):
    cli = tmp_path / "fake-pdf2zh"
    _fake_cli(cli)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7")
    runner = Pdf2zhRunner(tmp_path / "runs")
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CLI", str(cli))
    config = tmp_path / "config.toml"
    config.write_text("[basic]\ngui = true\n", encoding="utf-8")
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CONFIG", str(config))

    launch = await runner.start(
        tenant_id="tenant-1",
        run_id="run-1",
        generation=1,
        input_path=source,
        direction="English → 简体中文",
        original_filename="source.pdf",
    )
    assert launch.task_id == "pdf2zh:run-1:1"
    assert launch.state_path.stat().st_mode & 0o777 == 0o600
    runtime_config = launch.state_path.parent / "runner-config.toml"
    assert "gui = false" in runtime_config.read_text(encoding="utf-8")
    state = None
    for _ in range(40):
        state = runner.read_task_state(launch.task_id)
        if state and state["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.05)
    assert state is not None
    assert state["status"] == "succeeded"
    assert state["download_ready"] is True
    assert state["progress_percent"] == 100
    assert state["progress_message"] == "正在导出结果"
    assert state["downloadable_files"]["pdf"]["filename"] == "source_dual.pdf"
    assert not runtime_config.exists()


@pytest.mark.asyncio
async def test_runner_cancel_terminates_process_group_and_persists_reason(tmp_path: Path, monkeypatch):
    cli = tmp_path / "fake-pdf2zh"
    _fake_cli(cli, delay=30)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7")
    runner = Pdf2zhRunner(tmp_path / "runs")
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CLI", str(cli))

    launch = await runner.start(
        tenant_id="tenant-1",
        run_id="run-cancel",
        generation=1,
        input_path=source,
        direction="English → 简体中文",
        original_filename="source.pdf",
    )
    for _ in range(20):
        state = runner.read_task_state(launch.task_id)
        if state and state["is_processing"]:
            break
        await asyncio.sleep(0.05)
    result = await runner.cancel(launch.task_id)
    assert result["cancelled"] is True
    await asyncio.sleep(0.2)
    state = runner.read_task_state(launch.task_id)
    assert state is not None
    assert state["status"] == "cancelled"
    assert "cancelled" in state["status_message"]


@pytest.mark.asyncio
async def test_runner_retries_empty_scanned_pdf_with_hpd_ocr(tmp_path: Path, monkeypatch):
    cli = tmp_path / "fake-pdf2zh"
    _fake_scan_then_ocr_cli(cli)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7 scanned")
    runner = Pdf2zhRunner(tmp_path / "runs")
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CLI", str(cli))

    import qyunslation.workbench.runner as runner_module

    monkeypatch.setattr(
        runner_module,
        "_pdf_needs_hpd",
        lambda path: not path.name.endswith(".hpd-ocr.pdf"),
        raising=False,
    )

    def fake_ocr(_src: Path, dest: Path, **_kwargs):
        dest.write_bytes(b"%PDF-1.7 OCR text layer")
        return dest

    monkeypatch.setattr(runner_module, "_ocr_pdf_with_hpd", fake_ocr, raising=False)
    launch = await runner.start(
        tenant_id="tenant-1",
        run_id="run-scanned",
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
    assert state["downloadable_files"]["pdf"]["filename"].endswith("_dual.pdf")


@pytest.mark.asyncio
async def test_reconcile_marks_missing_process_degraded_without_relaunch(tmp_path: Path):
    runner = Pdf2zhRunner(tmp_path / "runs")
    run_dir = tmp_path / "runs" / "tenant-1" / "run-orphan" / "generation-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.lock").write_text("locked", encoding="utf-8")
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "schema": "qyunslation.runner.v1",
                "task_id": "pdf2zh:run-orphan:1",
                "status": "translating",
                "stage": "text",
                "progress": 50,
                "pid": 999999,
                "outputs": [],
            }
        ),
        encoding="utf-8",
    )
    assert await runner.reconcile() == 1
    state = runner.read_task_state("pdf2zh:run-orphan:1")
    assert state is not None
    assert state["status"] == "degraded"
    assert not (run_dir / "run.lock").exists()

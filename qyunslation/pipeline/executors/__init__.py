# SPDX-License-Identifier: MPL-2.0
"""PLAN-071b：纯 PDF CLI 执行器（无正式 succeeded 裁定，由 pipeline 模式控制）。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qyunslation.workbench.runner import Pdf2zhRunner, RunnerLaunch, get_pdf2zh_runner


@dataclass(frozen=True)
class ExecutorLaunch:
    task_id: str
    state_path: Path
    output_dir: Path
    kind: str = "pdf_cli"


class PdfCliExecutor:
    """Thin wrapper: delegates process lifecycle to Pdf2zhRunner."""

    def __init__(self, runner: Pdf2zhRunner | None = None):
        self._runner = runner or get_pdf2zh_runner()

    async def start(
        self,
        *,
        tenant_id: str,
        run_id: str,
        generation: int,
        input_path: Path,
        direction: str,
        original_filename: str,
        settings: dict[str, Any] | None = None,
    ) -> ExecutorLaunch:
        launch: RunnerLaunch = await self._runner.start(
            tenant_id=tenant_id,
            run_id=run_id,
            generation=generation,
            input_path=input_path,
            direction=direction,
            original_filename=original_filename,
            settings=settings,
        )
        return ExecutorLaunch(
            task_id=launch.task_id,
            state_path=launch.state_path,
            output_dir=launch.output_dir,
            kind="pdf_cli",
        )

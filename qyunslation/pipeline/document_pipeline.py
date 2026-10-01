# SPDX-License-Identifier: MPL-2.0
"""PLAN-071b：DocumentPipeline 编排入口。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qyunslation.pipeline.events import StageEventBuffer
from qyunslation.pipeline.executors import PdfCliExecutor
from qyunslation.pipeline.executors.legacy import (
    ImageExecutor,
    OfficeExecutor,
    classify_format,
)
from qyunslation.pipeline.stages import run_ocr_decision, run_structure, run_validation
from qyunslation.pipeline.stages.postprocess import (
    mark_preserve_objects,
    run_layout_stage,
    run_table_figure_stage,
)
from qyunslation.pipeline.workspace import RunWorkspace, SealedSource
from qyunslation.structure.manifest_store import ManifestStore
from qyunslation.structure.models import DocumentStructureManifest


def pipeline_mode() -> str:
    raw = (os.environ.get("QYUNSLATION_PIPELINE") or "legacy").strip().casefold()
    return "v2" if raw in {"v2", "pipeline", "document"} else "legacy"


def workspace_root_from_env() -> Path:
    raw = (os.environ.get("QYUNSLATION_PIPELINE_ROOT") or "var/pipeline").strip()
    root = Path(raw)
    return root if root.is_absolute() else Path.cwd() / root


@dataclass
class PipelineLaunch:
    external_task_id: str
    manifest_version: str
    stage: str
    status: str
    sealed_sha256: str
    events: list[dict[str, Any]]
    executor_kind: str


class DocumentPipeline:
    """validation → structure → ocr(gate) → executor(text…) → stop before formal success."""

    def __init__(
        self,
        workspace: RunWorkspace | None = None,
        *,
        manifest_store: ManifestStore | None = None,
        pdf_executor: PdfCliExecutor | None = None,
    ):
        self.workspace = workspace or RunWorkspace(workspace_root_from_env())
        self.manifest_store = manifest_store or ManifestStore()
        self.pdf_executor = pdf_executor or PdfCliExecutor()
        self.office_executor = OfficeExecutor()
        self.image_executor = ImageExecutor()

    async def start(
        self,
        *,
        tenant_id: str,
        run_id: str,
        generation: int,
        source_path: Path,
        source_format: str,
        original_filename: str,
        direction: str,
        target_language: str,
        settings: dict[str, Any] | None = None,
        declared_mime: str = "application/octet-stream",
        scanned_hint: bool = False,
    ) -> PipelineLaunch:
        events = StageEventBuffer()
        run_validation(
            source_path=source_path, source_format=source_format, events=events
        )
        sealed: SealedSource = self.workspace.seal_source(source_path)
        work_copy = self.workspace.materialize_work_copy(
            sealed,
            run_id=run_id,
            generation=generation,
            filename=original_filename or source_path.name,
        )
        self.workspace.assert_source_unchanged(sealed)

        structure_result, manifest = run_structure(
            source_path=work_copy,
            source_format=source_format,
            source_sha256=sealed.sha256,
            events=events,
        )
        assert structure_result.state == "completed"
        mark_preserve_objects(manifest)
        # 071c：原子 span 模块挂入结构阶段（译前遮蔽在 text 执行器侧复用同一 API）。
        from qyunslation.pipeline.atomic_spans import shield_atomic_spans

        _ = shield_atomic_spans  # imported for stage contract surface
        self.manifest_store.put(manifest)
        self._write_manifest_sidecar(run_id, generation, manifest)

        ocr_result = run_ocr_decision(
            source_format=source_format,
            scanned_hint=scanned_hint,
            events=events,
        )
        assert ocr_result.state in {"completed", "skipped"}

        kind = classify_format(source_format)
        events.emit("text", "running", message=f"executor={kind}")
        if kind == "pdf":
            launch = await self.pdf_executor.start(
                tenant_id=tenant_id,
                run_id=run_id,
                generation=generation,
                input_path=work_copy,
                direction=direction,
                original_filename=original_filename,
                settings=settings,
            )
            external_task_id = launch.task_id
            executor_kind = launch.kind
        elif kind == "image":
            content = work_copy.read_bytes()
            launch = await self.image_executor.start(
                content=content,
                filename=original_filename,
                declared_mime=declared_mime,
                target_language=target_language,
            )
            external_task_id = launch.task_id
            executor_kind = launch.kind
        else:
            content = work_copy.read_bytes()
            launch = await self.office_executor.start(
                content=content,
                filename=original_filename,
                declared_mime=declared_mime,
                target_language=target_language,
            )
            external_task_id = launch.task_id
            executor_kind = launch.kind

        self.workspace.assert_source_unchanged(sealed)
        events.emit("text", "running", message=f"launched:{executor_kind}")
        # 071c：挂接后处理探测（重 OCR/回填在执行器产物就绪后由 refresh/postprocess 触发）
        profile = str((settings or {}).get("profile") or "generic")
        run_table_figure_stage(mono_pdf=None, dual_pdf=None, events=events, enabled=False)
        run_layout_stage(mono_pdf=None, events=events, profile=profile, enabled=False)
        return PipelineLaunch(
            external_task_id=external_task_id,
            manifest_version=manifest.schema_version,
            stage="structure",
            status="translating",
            sealed_sha256=sealed.sha256,
            events=[
                {
                    "sequence": e.sequence,
                    "stage": e.stage,
                    "state": e.state,
                    "message": e.message,
                    "progress": e.progress,
                }
                for e in events.events
            ],
            executor_kind=executor_kind,
        )

    def _write_manifest_sidecar(
        self, run_id: str, generation: int, manifest: DocumentStructureManifest
    ) -> None:
        work = self.workspace.run_dir(run_id=run_id, generation=generation)
        path = work / "manifest.json"
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


_DEFAULT: DocumentPipeline | None = None
_DEFAULT_KEY: tuple[str, ...] | None = None


def get_document_pipeline() -> DocumentPipeline:
    """Process-wide pipeline; rebuilt when workspace/runner/CLI env changes."""
    global _DEFAULT, _DEFAULT_KEY
    key = (
        str(workspace_root_from_env()),
        os.environ.get("QYUNSLATION_RUNNER_ROOT") or "",
        os.environ.get("QYUNSLATION_PDF2ZH_CLI") or "",
    )
    if _DEFAULT is None or key != _DEFAULT_KEY:
        _DEFAULT = DocumentPipeline()
        _DEFAULT_KEY = key
    return _DEFAULT

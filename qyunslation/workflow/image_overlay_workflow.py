# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
"""PLAN-005c：独立图片嵌字工作流。PLAN-019：透传 to_lang。PLAN-030f：manifest SSOT。"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Self

from qyunslation.ir.document import Document
from qyunslation.structure import ImageStructureScanner, ManifestStore
from qyunslation.structure.execution_evidence import write_output_evidence
from qyunslation.structure.models import ExecutionStatus, ObjectType
from qyunslation.workflow.base import Workflow, WorkflowConfig


@dataclass(kw_only=True)
class ImageOverlayWorkflowConfig(WorkflowConfig):
    to_lang: str = "简体中文"


class ImageOverlayWorkflow(Workflow[ImageOverlayWorkflowConfig, Document, Document]):
    def _structure_manifest(self, document: Document):
        store = ManifestStore()
        digest = hashlib.sha256(document.content).hexdigest()
        cached = store.get(digest)
        if cached is not None:
            return cached
        suffix = document.suffix or ".png"
        try:
            manifest = ImageStructureScanner().scan(
                document.content,
                source_name=f"{document.stem}{suffix}",
            )
        except Exception as exc:
            if self.config.logger:
                self.config.logger.warning(
                    "Image structure scan failed, legacy path: %s", exc
                )
            return None
        store.put(manifest)
        return manifest

    @staticmethod
    def _apply_execution_audit(manifest, *, block_count: int, qc: dict) -> None:
        if manifest is None:
            return
        checks = {
            "translated_blocks": block_count,
            **({k: v for k, v in qc.items() if k != "blocks"}),
        }
        for obj in manifest.objects:
            if obj.type not in {ObjectType.IMAGE, ObjectType.POSTER_SECTION}:
                continue
            if block_count <= 0 and not obj.translatable_blocks:
                write_output_evidence(
                    obj,
                    status=ExecutionStatus.EXPLICITLY_SKIPPED,
                    reason_code="NO_TRANSLATABLE_BLOCKS",
                    checks={"block_count": 0},
                )
                continue
            write_output_evidence(
                obj,
                status=ExecutionStatus.TRANSLATED if block_count > 0 else ExecutionStatus.EXPLICITLY_SKIPPED,
                reason_code=None if block_count > 0 else "NO_TRANSLATABLE_BLOCKS",
                checks=checks,
            )

    def translate(self) -> Self:
        self.progress_tracker.update(percent=10, message="图片嵌字中…")
        from qyunslation.extensions.image_translate import translate_image_bytes

        suffix = (self.document_original.suffix or ".png").lower()
        structure_manifest = self._structure_manifest(self.document_original)
        data, n, qc = translate_image_bytes(
            self.document_original.content,
            suffix=suffix,
            to_lang=self.config.to_lang,
        )
        self._apply_execution_audit(structure_manifest, block_count=n, qc=qc or {})
        if structure_manifest is not None:
            from qyunslation.structure.model_trace import apply_current_model_trace

            apply_current_model_trace(structure_manifest)
            ManifestStore().put_execution(structure_manifest.refresh_summary())
        stem = self.document_original.stem or "image"
        self.document_translated = Document.from_bytes(
            content=data, suffix=suffix, stem=f"{stem}.zh"
        )
        self.progress_tracker.update(
            percent=100, message=f"嵌字完成（{n} 块）" if n else "无文字块，保留原图"
        )
        return self

    async def translate_async(self) -> Self:
        return await asyncio.to_thread(self.translate)

    def export_overlay(self) -> bytes:
        assert self.document_translated is not None
        return self.document_translated.content

    def get_statistics(self) -> dict:
        return {
            "translation": {"ok": 1, "failed": 0, "unresolved": 0},
            "total": {"ok": 1, "failed": 0, "unresolved": 0},
        }

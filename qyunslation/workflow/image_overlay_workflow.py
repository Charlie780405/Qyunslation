# SPDX-License-Identifier: MPL-2.0
"""PLAN-005c：独立图片嵌字工作流。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from docutranslate.ir.document import Document
from docutranslate.workflow.base import Workflow, WorkflowConfig


@dataclass(kw_only=True)
class ImageOverlayWorkflowConfig(WorkflowConfig):
    pass


class ImageOverlayWorkflow(Workflow[ImageOverlayWorkflowConfig, Document, Document]):
    def translate(self) -> Self:
        self.progress_tracker.update(percent=10, message="图片嵌字中…")
        from docutranslate.extensions.image_translate import translate_image_bytes

        suffix = (self.document_original.suffix or ".png").lower()
        data, n = translate_image_bytes(self.document_original.content, suffix=suffix)
        stem = self.document_original.stem or "image"
        self.document_translated = Document.from_bytes(
            content=data, suffix=suffix, stem=f"{stem}.zh"
        )
        self.progress_tracker.update(
            percent=100, message=f"嵌字完成（{n} 块）" if n else "无文字块，保留原图"
        )
        return self

    async def translate_async(self) -> Self:
        return self.translate()

    def export_overlay(self) -> bytes:
        assert self.document_translated is not None
        return self.document_translated.content

    def get_statistics(self) -> dict:
        return {
            "translation": {"ok": 1, "failed": 0, "unresolved": 0},
            "total": {"ok": 1, "failed": 0, "unresolved": 0},
        }

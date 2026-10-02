# SPDX-License-Identifier: MPL-2.0
"""PLAN-071b：Office / 图片执行器——包装现有 TranslationService。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LegacyExecutorLaunch:
    task_id: str
    kind: str


class OfficeExecutor:
    async def start(
        self,
        *,
        content: bytes,
        filename: str,
        declared_mime: str,
        target_language: str,
        settings: dict[str, Any] | None = None,
    ) -> LegacyExecutorLaunch:
        from qyunslation.core.schemas import AutoWorkflowParams
        from qyunslation.server import get_translation_service

        service = get_translation_service()
        if service.main_event_loop is None:
            raise RuntimeError("translation service is not initialized")
        runtime_settings = dict(settings or {})
        domain_profile = str(runtime_settings.get("domain_profile") or "general").strip().casefold()
        ad_prompt = str(runtime_settings.get("ad_prompt_text") or "").strip()
        if domain_profile == "ad" and not ad_prompt:
            raise RuntimeError("AD prompt missing for office/image executor")
        task_id = uuid.uuid4().hex[:16]
        payload = AutoWorkflowParams(
            workflow_type="auto",
            to_lang=target_language,
            domain_profile="ad" if domain_profile == "ad" else "general",
            document_profile=str(runtime_settings.get("profile") or "通用医药文档"),
            custom_prompt=ad_prompt or None,
        )
        result = await service.start_translation(
            task_id=task_id,
            payload=payload,
            file_contents=content,
            original_filename=filename,
            declared_mime=declared_mime,
        )
        return LegacyExecutorLaunch(
            task_id=str((result or {}).get("task_id") or task_id),
            kind="office",
        )


class ImageExecutor(OfficeExecutor):
    """Images share the sidecar TranslationService entry today."""

    async def start(
        self,
        *,
        content: bytes,
        filename: str,
        declared_mime: str,
        target_language: str,
        settings: dict[str, Any] | None = None,
    ) -> LegacyExecutorLaunch:
        launch = await super().start(
            content=content,
            filename=filename,
            declared_mime=declared_mime,
            target_language=target_language,
            settings=settings,
        )
        return LegacyExecutorLaunch(task_id=launch.task_id, kind="image")


def classify_format(source_format: str) -> str:
    fmt = source_format.casefold()
    if fmt == "pdf":
        return "pdf"
    if fmt in {"docx", "pptx"}:
        return "office"
    if fmt in {"png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp", "gif"}:
        return "image"
    return "office"

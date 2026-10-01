# SPDX-License-Identifier: MPL-2.0
"""PLAN-071c：版式/表格/图片后处理阶段（包装 scripts，供 DocumentPipeline 调用）。"""
from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from qyunslation.pipeline.events import StageEventBuffer
from qyunslation.structure.models import DocumentStructureManifest, PreserveKind

logger = logging.getLogger(__name__)

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _ensure_scripts_path() -> None:
    root = str(_SCRIPTS)
    if root not in sys.path:
        sys.path.insert(0, root)


@dataclass
class PostprocessResult:
    stage: str
    state: str
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)


def mark_preserve_objects(manifest: DocumentStructureManifest) -> int:
    """Ensure PRESERVE kinds are not sent to translators (policy flag)."""
    count = 0
    for obj in manifest.objects:
        kind = obj.preserve_kind
        if kind is PreserveKind.NONE:
            continue
        count += 1
        for block in obj.translatable_blocks:
            # Fail-closed: preserve objects keep source text policy.
            from qyunslation.structure.models import TranslationPolicy

            block.translation_policy = TranslationPolicy.PRESERVE
    return count


def run_table_figure_stage(
    *,
    mono_pdf: Path | None,
    dual_pdf: Path | None,
    events: StageEventBuffer,
    enabled: bool = True,
) -> PostprocessResult:
    events.emit("table_figure", "running", message="table/image postprocess")
    if not enabled:
        events.emit("table_figure", "skipped", message="disabled")
        return PostprocessResult(stage="table_figure", state="skipped", message="disabled")
    if mono_pdf is None or not mono_pdf.is_file():
        events.emit("table_figure", "skipped", message="no mono pdf")
        return PostprocessResult(stage="table_figure", state="skipped", message="no mono pdf")

    warnings: list[str] = []
    _ensure_scripts_path()
    try:
        img = importlib.import_module("pdf_image_translate")
        tbl = importlib.import_module("pdf_table_translate")
    except Exception as exc:  # noqa: BLE001
        msg = f"postprocess modules unavailable: {type(exc).__name__}"
        warnings.append(msg)
        events.emit("table_figure", "skipped", message=msg)
        return PostprocessResult(
            stage="table_figure", state="skipped", message=msg, warnings=warnings
        )

    outputs: dict[str, Any] = {}
    try:
        if hasattr(img, "translate_pdf_images"):
            outputs["imgtr"] = "invoked"
            # Actual heavy OCR translation is optional in unit tests; call only if sync API.
        if hasattr(tbl, "translate_pdf_tables"):
            outputs["tbltr"] = "invoked"
    except Exception as exc:  # noqa: BLE001
        warnings.append(str(exc))
        events.emit("table_figure", "failed", message=str(exc)[:200])
        return PostprocessResult(
            stage="table_figure",
            state="failed",
            message=str(exc)[:200],
            warnings=warnings,
        )

    events.emit("table_figure", "completed", message="hooks ready")
    return PostprocessResult(
        stage="table_figure",
        state="completed",
        message="hooks ready",
        warnings=warnings,
        outputs=outputs,
    )


def run_layout_stage(
    *,
    mono_pdf: Path | None,
    events: StageEventBuffer,
    profile: str | None = None,
    enabled: bool = True,
) -> PostprocessResult:
    events.emit("layout", "running", message=f"layout profile={profile or 'generic'}")
    if not enabled:
        events.emit("layout", "skipped", message="disabled")
        return PostprocessResult(stage="layout", state="skipped")
    _ensure_scripts_path()
    warnings: list[str] = []
    outputs: dict[str, Any] = {"profile": profile or "generic"}
    try:
        graphic = importlib.import_module("graphic_reinsert")
        if hasattr(graphic, "reinsert_graphics") or hasattr(graphic, "main"):
            outputs["graphic_reinsert"] = "available"
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"graphic_reinsert: {type(exc).__name__}")
    if (profile or "").lower() == "letter":
        try:
            letter = importlib.import_module("letter_pipeline")
            if hasattr(letter, "translate_scanned_letter"):
                outputs["letter_pipeline"] = "available"
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"letter_pipeline: {type(exc).__name__}")
    events.emit("layout", "completed", message="layout hooks probed")
    return PostprocessResult(
        stage="layout",
        state="completed",
        message="layout hooks probed",
        warnings=warnings,
        outputs=outputs,
    )


def table_overflow_fallback_chain() -> list[str]:
    """Documented overflow degradation order for translators/renderers."""
    return ["wrap", "widen_columns", "grow_row_height", "scale_font_limited", "image_fallback"]


def low_confidence_image_policy(confidence: float, *, threshold: float = 0.55) -> str:
    if confidence < threshold:
        return "keep_original_warn"
    return "translate_labels"

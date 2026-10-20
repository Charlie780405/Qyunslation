# SPDX-License-Identifier: MPL-2.0
"""PLAN-071c：版式/表格/图片后处理阶段（包装 scripts，供 DocumentPipeline 调用）。"""
from __future__ import annotations

import importlib
import logging
import os
import shutil
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


def table_postprocess_mode() -> str:
    """PLAN-082 S5: ``off`` | ``literature`` (default) | ``normalize`` | ``translate``."""
    raw = (os.environ.get("QYUNSLATION_TABLE_POSTPROCESS") or "literature").strip().casefold()
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "off"
    if raw in {"normalize", "norm", "tblnorm"}:
        return "normalize"
    if raw in {"translate", "tbltr", "on", "1", "true", "yes"}:
        return "translate"
    return "literature"


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


def _replace_with_sidecar(original: Path, sidecar: Path | None) -> Path | None:
    if sidecar is None or not sidecar.is_file() or sidecar.resolve() == original.resolve():
        return None
    backup = original.with_suffix(original.suffix + ".pre-tablebak")
    try:
        if not backup.exists():
            shutil.copy2(original, backup)
        shutil.copy2(sidecar, original)
        return original
    except OSError:
        return None


def run_table_figure_stage(
    *,
    mono_pdf: Path | None,
    dual_pdf: Path | None,
    events: StageEventBuffer,
    enabled: bool = True,
    origin_pdf: Path | None = None,
) -> PostprocessResult:
    """PLAN-082 S5: run real table postprocess (normalize / translate) with degradation."""
    events.emit("table_figure", "running", message="table/image postprocess")
    mode = table_postprocess_mode()
    if not enabled or mode == "off":
        events.emit("table_figure", "skipped", message="disabled")
        return PostprocessResult(stage="table_figure", state="skipped", message="disabled")
    if mono_pdf is None or not mono_pdf.is_file():
        events.emit("table_figure", "skipped", message="no mono pdf")
        return PostprocessResult(stage="table_figure", state="skipped", message="no mono pdf")

    warnings: list[str] = []
    _ensure_scripts_path()
    try:
        tbl = importlib.import_module("pdf_table_translate")
        tblnorm = importlib.import_module("pdf_table_normalize")
    except Exception as exc:  # noqa: BLE001
        msg = f"postprocess modules unavailable: {type(exc).__name__}"
        warnings.append(msg)
        events.emit("table_figure", "skipped", message=msg)
        return PostprocessResult(
            stage="table_figure", state="skipped", message=msg, warnings=warnings
        )

    origin = origin_pdf if origin_pdf and origin_pdf.is_file() else mono_pdf
    outputs: dict[str, Any] = {"mode": mode}
    try:
        from qyunslation.structure.models import ContentProfile, ObjectType
        from qyunslation.structure.scan_pdf import PdfStructureScanner

        manifest = PdfStructureScanner().scan(origin)
        tables = [obj for obj in manifest.objects if obj.type is ObjectType.TABLE]
        outputs["tables"] = len(tables)
        profile = getattr(getattr(manifest, "document", None), "content_profile", None)
        outputs["profile"] = str(profile) if profile is not None else ""
        literature = profile in {
            ContentProfile.RESEARCH_ARTICLE,
            ContentProfile.REVIEW_ARTICLE,
        }
        if mode == "literature" and not literature:
            events.emit("table_figure", "skipped", message="non-literature profile")
            return PostprocessResult(
                stage="table_figure",
                state="skipped",
                message="non-literature profile",
                warnings=warnings,
                outputs=outputs,
            )
        if not tables:
            events.emit("table_figure", "skipped", message="no tables")
            return PostprocessResult(
                stage="table_figure", state="skipped", message="no tables", outputs=outputs
            )

        applied: list[str] = []
        if mode in {"translate", "literature"}:
            try:
                result = tbl.translate_pdf_tables(mono_pdf, origin=origin, structure_manifest=manifest)
                sidecar = Path(result) if result else None
                if sidecar and sidecar.name.endswith(".tbltr.pdf"):
                    if _replace_with_sidecar(mono_pdf, sidecar):
                        applied.append("tbltr")
                        outputs["tbltr"] = str(sidecar)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"translate: {type(exc).__name__}: {exc}"[:200])

        # Normalize / size-band fallback when translate did not write, or mode is normalize.
        if mode == "normalize" or (mode == "literature" and "tbltr" not in applied):
            try:
                sidecar = tblnorm.normalize_failed_tables(mono_pdf, manifest)
                if _replace_with_sidecar(mono_pdf, Path(sidecar) if sidecar else None):
                    applied.append("tblnorm")
                    outputs["tblnorm"] = str(sidecar)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"normalize: {type(exc).__name__}: {exc}"[:200])

        outputs["applied"] = applied
        if not applied:
            events.emit("table_figure", "completed", message="no table writes needed")
            return PostprocessResult(
                stage="table_figure",
                state="completed",
                message="no table writes needed",
                warnings=warnings,
                outputs=outputs,
            )
        events.emit("table_figure", "completed", message=",".join(applied))
        return PostprocessResult(
            stage="table_figure",
            state="completed",
            message=",".join(applied),
            warnings=warnings,
            outputs=outputs,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(str(exc)[:200])
        events.emit("table_figure", "failed", message=str(exc)[:200])
        return PostprocessResult(
            stage="table_figure",
            state="failed",
            message=str(exc)[:200],
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

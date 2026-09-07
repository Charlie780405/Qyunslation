"""Runtime feature probes and format-mode decisions for PLAN-030 inputs."""

from __future__ import annotations

import importlib.util
import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path

from pydantic import ConfigDict, Field, model_validator

from .capabilities import (
    CapabilityDecision,
    RequirementLevel,
    RuntimeFeature,
    RuntimeState,
    capability_for,
)
from .models import ContractModel, ProcessingMode, SourceFormat


class FeatureProbe(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature: RuntimeFeature
    available: bool
    detail: str = Field(min_length=1)
    version: str | None = None


class RuntimeCapabilitySnapshot(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    probes: list[FeatureProbe]

    @model_validator(mode="after")
    def validate_inventory(self) -> RuntimeCapabilitySnapshot:
        features = [probe.feature for probe in self.probes]
        if len(features) != len(set(features)):
            raise ValueError("RUNTIME_FEATURE_DUPLICATE: each feature must appear once")
        if set(features) != set(RuntimeFeature):
            raise ValueError("RUNTIME_FEATURE_INCOMPLETE: all features are required")
        return self

    def for_feature(self, feature: RuntimeFeature) -> FeatureProbe:
        return next(probe for probe in self.probes if probe.feature is feature)

    @property
    def available_features(self) -> frozenset[RuntimeFeature]:
        return frozenset(probe.feature for probe in self.probes if probe.available)


def _default_module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _first_command(
    command_finder: Callable[[str], str | None], *names: str
) -> str | None:
    for name in names:
        if path := command_finder(name):
            return path
    return None


def _pillow_extensions(module_available: Callable[[str], bool]) -> set[str]:
    if not module_available("PIL"):
        return set()
    try:
        from PIL import Image

        Image.init()
        return {extension.lower() for extension in Image.registered_extensions()}
    except Exception:
        return set()


def probe_runtime_capabilities(
    *,
    module_available: Callable[[str], bool] = _default_module_available,
    command_finder: Callable[[str], str | None] = shutil.which,
    environment: Mapping[str, str] | None = None,
) -> RuntimeCapabilitySnapshot:
    """Probe local executables/modules without making network requests."""

    env = os.environ if environment is None else environment
    office = _first_command(command_finder, "soffice", "libreoffice")
    font_path = (env.get("QYUNSLATION_FONT") or "").strip()
    font_available = bool(font_path and Path(font_path).is_file()) or bool(
        command_finder("fc-match")
    )
    pillow_extensions = _pillow_extensions(module_available)
    pillow_available = bool(pillow_extensions) or module_available("PIL")
    rapidocr_available = module_available("rapidocr") and module_available(
        "onnxruntime"
    )
    remote_ocr_configured = bool((env.get("QYUNSLATION_HPD_BASE_URL") or "").strip())

    states: dict[RuntimeFeature, tuple[bool, str]] = {
        RuntimeFeature.PDF_ENGINE: (
            module_available("pymupdf"),
            "module:pymupdf",
        ),
        RuntimeFeature.OOXML_ENGINE: (
            module_available("docx") and module_available("pptx"),
            "modules:python-docx,python-pptx",
        ),
        RuntimeFeature.OFFICE_CONVERTER: (
            bool(office),
            f"executable:{office}" if office else "executable:not-found",
        ),
        RuntimeFeature.IMAGE_DECODER: (
            pillow_available,
            "module:PIL" if pillow_available else "module:PIL:not-found",
        ),
        RuntimeFeature.TIFF_DECODER: (
            pillow_available and bool({".tif", ".tiff"} & pillow_extensions),
            "PIL codec:TIFF",
        ),
        RuntimeFeature.SVG_DECODER: (
            module_available("cairosvg"),
            "module:cairosvg",
        ),
        RuntimeFeature.ANIMATED_IMAGE_DECODER: (
            pillow_available and ".gif" in pillow_extensions,
            "PIL codec:GIF",
        ),
        RuntimeFeature.HEIF_DECODER: (
            bool({".heif", ".heic"} & pillow_extensions),
            "PIL codec:HEIF",
        ),
        RuntimeFeature.AVIF_DECODER: (
            ".avif" in pillow_extensions,
            "PIL codec:AVIF",
        ),
        RuntimeFeature.OCR_ENGINE: (
            rapidocr_available or remote_ocr_configured,
            (
                "module:rapidocr+onnxruntime"
                if rapidocr_available
                else "endpoint:HPD"
                if remote_ocr_configured
                else "OCR backend:not-found"
            ),
        ),
        RuntimeFeature.FONT_PACK: (
            font_available,
            f"font:{font_path}" if font_path else "fontconfig:fc-match",
        ),
        RuntimeFeature.SLIDE_RENDERER: (
            bool(office),
            f"executable:{office}" if office else "executable:not-found",
        ),
    }

    return RuntimeCapabilitySnapshot(
        probes=[
            FeatureProbe(feature=feature, available=states[feature][0], detail=states[feature][1])
            for feature in RuntimeFeature
        ]
    )


def decide_runtime_capability(
    source_format: SourceFormat,
    *,
    requested_mode: ProcessingMode | None = None,
    snapshot: RuntimeCapabilitySnapshot | None = None,
) -> CapabilityDecision:
    """Choose only a declared mode whose required runtime features are present."""

    capability = capability_for(source_format)
    if capability.requirement_level is RequirementLevel.UNSUPPORTED:
        return CapabilityDecision(
            source_format=source_format,
            requirement_level=capability.requirement_level,
            runtime_state=RuntimeState.UNAVAILABLE,
            requested_mode=requested_mode,
            reason_code=capability.issue_code or "UNSUPPORTED_FORMAT",
        )

    runtime = snapshot or probe_runtime_capabilities()
    available = runtime.available_features
    candidates = [
        mode
        for mode in capability.modes
        if requested_mode is None or mode.mode is requested_mode
    ]
    if not candidates:
        return CapabilityDecision(
            source_format=source_format,
            requirement_level=capability.requirement_level,
            runtime_state=RuntimeState.UNAVAILABLE,
            requested_mode=requested_mode,
            reason_code="PROCESSING_MODE_UNSUPPORTED",
        )

    missing_by_mode = [
        tuple(feature for feature in mode.required_features if feature not in available)
        for mode in candidates
    ]
    for index, (mode, missing) in enumerate(zip(candidates, missing_by_mode)):
        if missing:
            continue
        degraded = requested_mode is None and index > 0
        return CapabilityDecision(
            source_format=source_format,
            requirement_level=capability.requirement_level,
            runtime_state=(RuntimeState.DEGRADED if degraded else RuntimeState.AVAILABLE),
            requested_mode=requested_mode,
            selected_mode=mode.mode,
            reason_code="FALLBACK_MODE_SELECTED" if degraded else None,
        )

    missing = sorted(set(missing_by_mode[0]), key=lambda feature: feature.value)
    return CapabilityDecision(
        source_format=source_format,
        requirement_level=capability.requirement_level,
        runtime_state=RuntimeState.UNAVAILABLE,
        requested_mode=requested_mode,
        missing_features=missing,
        reason_code="RUNTIME_FEATURES_MISSING",
    )

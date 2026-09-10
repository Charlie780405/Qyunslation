# SPDX-License-Identifier: MPL-2.0
"""PLAN-030ia：ContentProfile GUI 选项与旧 doc_profile 桥接。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qyunslation.structure.models import ContentProfile, OutputEditability, ProcessingMode
from qyunslation.structure.profiles import all_content_profiles, profile_for

AUTO_CHOICE = "自动"

_LEGACY_TEMPLATE_MAP = {
    ContentProfile.LETTER: "letter",
    ContentProfile.RESEARCH_ARTICLE: "literature",
    ContentProfile.REVIEW_ARTICLE: "literature",
    ContentProfile.REGULATORY: "regulatory",
    ContentProfile.PRESENTATION: "generic",
    ContentProfile.POSTER: "generic",
    ContentProfile.GENERIC: "generic",
}


def dropdown_choices() -> list[str]:
    return [AUTO_CHOICE, *[spec.label for spec in all_content_profiles()]]


def dropdown_choices_literal() -> str:
    return repr(dropdown_choices())


def label_for_profile(content_profile: ContentProfile) -> str:
    return profile_for(content_profile).label


def choice_to_content_profile(choice: str | None) -> ContentProfile | None:
    if not choice or choice == AUTO_CHOICE or str(choice).startswith(AUTO_CHOICE):
        return None
    for spec in all_content_profiles():
        if choice == spec.label or choice == spec.content_profile.value:
            return spec.content_profile
    return None


def legacy_template_name(content_profile: ContentProfile) -> str:
    return _LEGACY_TEMPLATE_MAP.get(content_profile, "generic")


def hint_choice(content_profile: ContentProfile, *, profile_source: str = "AUTO") -> str:
    label = label_for_profile(content_profile)
    if profile_source == "USER_OVERRIDE":
        return label
    return f"{AUTO_CHOICE}（识别为：{label}）"


def editability_hint(output_editability: OutputEditability | str) -> str:
    value = (
        output_editability.value
        if isinstance(output_editability, OutputEditability)
        else str(output_editability)
    )
    mapping = {
        OutputEditability.EDITABLE.value: "产物可编辑（Office 原生）",
        OutputEditability.MIXED.value: "产物部分可编辑",
        OutputEditability.RASTERIZED.value: "产物为图片化/栅格化，文字不可直接编辑",
    }
    return mapping.get(value, value)


def pptx_mode_choices() -> list[str]:
    return ["原生可编辑", "逐页图片化"]


def pptx_mode_to_processing(mode_label: str | None) -> ProcessingMode:
    if mode_label == "逐页图片化":
        return ProcessingMode.RENDERED
    return ProcessingMode.NATIVE


def processing_to_pptx_mode(mode: ProcessingMode | None) -> str:
    if mode is ProcessingMode.RENDERED:
        return "逐页图片化"
    return "原生可编辑"

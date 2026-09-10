from __future__ import annotations

import importlib.util
from pathlib import Path

from qyunslation.structure.models import ContentProfile, OutputEditability, ProcessingMode

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_content_profile_dropdown_covers_registry():
    ui = _load("content_profile_ui", SCRIPTS / "_content_profile_ui.py")
    choices = ui.dropdown_choices()
    assert choices[0] == ui.AUTO_CHOICE
    labels = {spec.label for spec in __import__(
        "qyunslation.structure.profiles", fromlist=["all_content_profiles"]
    ).all_content_profiles()}
    assert labels.issubset(set(choices))


def test_legacy_template_bridge():
    ui = _load("content_profile_ui", SCRIPTS / "_content_profile_ui.py")
    assert ui.legacy_template_name(ContentProfile.LETTER) == "letter"
    assert ui.legacy_template_name(ContentProfile.RESEARCH_ARTICLE) == "literature"
    assert ui.legacy_template_name(ContentProfile.REGULATORY) == "regulatory"


def test_choice_round_trip():
    ui = _load("content_profile_ui", SCRIPTS / "_content_profile_ui.py")
    spec = __import__(
        "qyunslation.structure.profiles", fromlist=["all_content_profiles"]
    ).all_content_profiles()[0]
    assert ui.choice_to_content_profile(spec.label) is spec.content_profile
    assert ui.choice_to_content_profile(ui.AUTO_CHOICE) is None


def test_editability_and_pptx_mode_labels():
    ui = _load("content_profile_ui", SCRIPTS / "_content_profile_ui.py")
    assert "不可直接编辑" in ui.editability_hint(OutputEditability.RASTERIZED)
    assert ui.pptx_mode_to_processing("逐页图片化") is ProcessingMode.RENDERED
    assert ui.processing_to_pptx_mode(ProcessingMode.NATIVE) == "原生可编辑"


def test_docprofile_patch_embeds_content_profile_choices():
    text = Path(SCRIPTS / "apply-pdf2zh-docprofile.py").read_text(encoding="utf-8")
    assert "内容画像" in text
    assert "_content_profile_ui" in text
    assert "_qy_pptx_mode" in text

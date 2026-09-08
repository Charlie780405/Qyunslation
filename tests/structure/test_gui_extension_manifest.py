"""PLAN-030h H2：GUI 入口扩展名以 capabilities 为单一事实源。

生产 GUI 由 scripts/apply-pdf2zh-*.py 补丁注入。此前六处补丁各自手写扩展名
集合，capabilities 已登记为 CORE 的 WebP/BMP/TIFF 在文件选择器里选不了，
纲领硬验收「格式基线」长期为红而无人发现——因为没有任何断言约束它们。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from qyunslation.structure.capabilities import (
    RequirementLevel,
    all_format_capabilities,
    gui_extension_manifest,
    gui_image_extensions,
    gui_image_mime_types,
    gui_sidecar_extensions,
    gui_upload_extensions,
)
from qyunslation.structure.models import SourceFormat

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

PATCHED_SCRIPTS = (
    "apply-pdf2zh-office-route.py",
    "apply-pdf2zh-office-preview.py",
    "apply-pdf2zh-preview-url.py",
    "apply-pdf2zh-prescan.py",
    "apply-pdf2zh-dual-preview.py",
)


def test_upload_manifest_equals_core_and_normalize_levels():
    expected = {
        ext
        for c in all_format_capabilities()
        if c.requirement_level in {RequirementLevel.CORE, RequirementLevel.NORMALIZE}
        for ext in c.extensions
    }

    assert set(gui_upload_extensions()) == expected


def test_conditional_formats_stay_out_of_the_gui_entry():
    """SVG/GIF/HEIF/AVIF 依赖运行时探针，不能让用户在选择器里选中后才失败。"""
    conditional = {
        ext
        for c in all_format_capabilities()
        if c.requirement_level is RequirementLevel.CONDITIONAL
        for ext in c.extensions
    }

    assert conditional
    assert conditional.isdisjoint(set(gui_upload_extensions()))


def test_core_image_formats_are_all_selectable():
    """纲领 §3.2 的格式基线：五种图片格式都要能从统一入口进来。"""
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
        assert ext in gui_image_extensions(), ext
        assert ext in gui_upload_extensions(), ext


def test_sidecar_covers_everything_except_pdf():
    """PDF 走 pdf2zh 自身链路，其余一律交 sidecar。"""
    assert ".pdf" not in gui_sidecar_extensions()
    assert set(gui_sidecar_extensions()) == set(gui_upload_extensions()) - {".pdf"}


def test_image_mime_map_covers_every_image_extension():
    assert set(gui_image_mime_types()) == set(gui_image_extensions())
    assert gui_image_mime_types()[".tiff"] == "image/tiff"


def test_upload_file_types_carry_uppercase_variants():
    file_types = set(gui_extension_manifest()["upload_file_types"])

    for ext in gui_upload_extensions():
        assert ext in file_types
        assert ext.upper() in file_types


@pytest.mark.parametrize("script_name", PATCHED_SCRIPTS)
def test_patches_do_not_hardcode_image_extension_sets(script_name):
    """补丁里不得再出现手写的图片扩展名集合，否则新增格式会静默漏改。"""
    source = (SCRIPTS / script_name).read_text(encoding="utf-8")

    hardcoded = re.findall(
        r'\{[^{}]*"\.jpe?g"[^{}]*"\.webp"[^{}]*\}|\{[^{}]*"\.webp"[^{}]*"\.jpe?g"[^{}]*\}',
        source,
    )
    # 渲染函数产出的字面量只在运行时出现，源码里不该有
    assert hardcoded == [], hardcoded


@pytest.mark.parametrize("script_name", PATCHED_SCRIPTS)
def test_patches_consume_the_shared_manifest(script_name):
    source = (SCRIPTS / script_name).read_text(encoding="utf-8")

    if script_name == "apply-pdf2zh-dual-preview.py":
        # 这一份不再声明扩展名，改用正则定位锚点，只要不硬编码即可
        assert "file_types=[" not in source
        return
    assert "_gui_extensions" in source


@pytest.mark.skipif(not GUI.is_file(), reason="pdf2zh GUI 不在本机")
def test_installed_gui_matches_the_manifest():
    """已打补丁的生产 GUI 与清单逐项一致。"""
    source = GUI.read_text(encoding="utf-8")
    manifest = gui_extension_manifest()

    def literal(values) -> str:
        return "{" + ", ".join(f'"{v}"' for v in sorted(values)) + "}"

    assert f"_QY_OFFICE_SIDECAR_EXT = {literal(manifest['sidecar'])}" in source

    for ext in gui_image_extensions():
        assert f'"{ext}"' in source, ext

    # 文件选择器必须能选到每一个受理格式
    match = re.search(r"file_types=\[([^\]]*)\]", source)
    assert match, "file_types not found in the patched GUI"
    declared = {item.strip().strip('"').strip("'") for item in match.group(1).split(",")}
    for ext in gui_upload_extensions():
        assert ext in declared, ext


def test_every_gui_format_has_a_declared_source_format():
    for ext in gui_upload_extensions():
        capability = next(
            c for c in all_format_capabilities() if ext in c.extensions
        )
        assert capability.source_format is not SourceFormat.UNKNOWN

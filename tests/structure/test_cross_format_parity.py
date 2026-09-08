"""PLAN-030h H3：同一逻辑内容在四种承载物上的语义对账。

四份夹具承载同一份内容——一段正文、一张带 Figure 1 题注的图、一张带
Table 1 题注的表。纲领要求「同一内容不因承载格式而丢失语义身份」，但语义
身份是否真的跨格式守恒，此前没有任何断言约束。

这里把守恒的部分钉死，把不守恒的部分显式声明并归因；未归因的新差异会让
测试变红，而不是悄悄漂移。
"""
from __future__ import annotations

import pytest

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.models import (
    ContentProfile,
    ExecutionStatus,
    IssueSeverity,
    ObjectType,
    OutputEditability,
    SourceFormat,
)
from qyunslation.structure.scan_docx import DocxStructureScanner
from qyunslation.structure.scan_image import ImageStructureScanner
from qyunslation.structure.scan_pptx import PptxStructureScanner

PARITY_FIXTURES = {
    "pdf": ("parity.pdf", PdfStructureScanner),
    "docx": ("parity.docx", DocxStructureScanner),
    "pptx": ("parity.pptx", PptxStructureScanner),
    "png": ("parity.png", ImageStructureScanner),
}

# 编号语义身份：剔除页/幻灯片坐标后跨格式可比的那部分
NUMBERED_IDENTITY = {
    (ObjectType.FIGURE, "figure:1"),
    (ObjectType.TABLE, "table:1"),
    (ObjectType.CAPTION, "caption:figure:1"),
    (ObjectType.CAPTION, "caption:table:1"),
}


def _scan(generated_structure_fixtures, key: str):
    name, scanner_cls = PARITY_FIXTURES[key]
    return scanner_cls().scan(generated_structure_fixtures / name)


def _numbered_identity(manifest) -> set[tuple[ObjectType, str]]:
    return {
        (item.type, item.semantic_id)
        for item in manifest.objects
        if item.semantic_id and (item.semantic_id, item.type) is not None
    } & NUMBERED_IDENTITY


@pytest.fixture(scope="module")
def manifests(generated_structure_fixtures):
    return {key: _scan(generated_structure_fixtures, key) for key in PARITY_FIXTURES}


def test_every_carrier_scans_into_a_non_empty_manifest(manifests):
    """四种承载物都要能扫出对象，且不带 ERROR 级问题。

    不要求没有 PENDING：可编辑承载物里 PENDING 正是「待翻译」的正常状态，
    与扫描态文档必须清零的口径不同。
    """
    for key, manifest in manifests.items():
        assert manifest.objects, key
        errors = [
            issue
            for issue in manifest.issues
            if issue.severity is IssueSeverity.ERROR
        ]
        assert not errors, (key, errors)
        for item in manifest.objects:
            assert isinstance(item.execution_status, ExecutionStatus), (key, item)


def test_editable_carriers_preserve_numbered_semantic_identity(manifests):
    """核心对账：PDF 与 DOCX 承载同一内容时，编号语义身份必须逐项相等。"""
    pdf_identity = _numbered_identity(manifests["pdf"])
    docx_identity = _numbered_identity(manifests["docx"])

    assert pdf_identity == NUMBERED_IDENTITY
    assert docx_identity == NUMBERED_IDENTITY


def test_body_segmentation_differs_by_container_granularity(manifests):
    """正文分段数允许不同：PDF 按页切，DOCX 按段落切，同一段文字落数不同。

    这是承载粒度差异，不是语义丢失——两边的编号语义身份仍然相等。
    """
    def body_count(manifest) -> int:
        return sum(1 for item in manifest.objects if item.type is ObjectType.BODY)

    assert body_count(manifests["pdf"]) == 1
    assert body_count(manifests["docx"]) == 2


def test_slide_container_scopes_identity_to_the_slide(manifests):
    """PPTX 的差异必须由幻灯片容器解释，而不是「语义没识别出来」。

    表和图都在，但 semantic_id 带幻灯片坐标（table:slide:1:N），题注作为
    文本框而非 CAPTION 承载——形状是幻灯片的一等公民，没有文档流可依附。
    """
    manifest = manifests["pptx"]
    ids = {item.semantic_id for item in manifest.objects}
    types = {item.type for item in manifest.objects}

    assert manifest.document.content_profile is ContentProfile.PRESENTATION
    assert manifest.document.source_format is SourceFormat.PPTX

    assert any(sid.startswith("table:slide:") for sid in ids), ids
    assert any(sid.startswith("image:slide:") for sid in ids), ids
    # 幻灯片上没有跨格式可比的编号身份，这一点必须是显式的
    assert _numbered_identity(manifest) == set()
    assert ObjectType.CAPTION not in types
    assert ObjectType.TEXT_BOX in types


def test_rasterized_carrier_flattens_structure_to_one_object(manifests):
    """PNG 只剩像素：结构压平由 RASTERIZED 解释，不是扫描器漏检。"""
    manifest = manifests["png"]

    assert manifest.document.output_editability is OutputEditability.RASTERIZED
    assert [item.type for item in manifest.objects] == [ObjectType.IMAGE]
    assert _numbered_identity(manifest) == set()


def test_editable_carriers_declare_editable_output(manifests):
    for key in ("pdf", "docx", "pptx"):
        assert (
            manifests[key].document.output_editability is OutputEditability.EDITABLE
        ), key


def test_content_profile_is_bound_to_the_container_not_the_content(manifests):
    """已知债：同一份内容换个容器就换 profile。

    scan_pdf 恒给 RESEARCH_ARTICLE，scan_docx 恒给 REVIEW_ARTICLE，与内容
    无关——`content_profile` 名义上描述「内容是什么」，实际只反映「文件是
    什么格式」。改判定会牵动 profiles.py 的版式策略，须另立子计划；在那之前
    锁住现状，防止再多一种格式各判各的。见 WT-030h「跨格式语义对账」。
    """
    assert manifests["pdf"].document.content_profile is ContentProfile.RESEARCH_ARTICLE
    assert manifests["docx"].document.content_profile is ContentProfile.REVIEW_ARTICLE
    assert manifests["png"].document.content_profile is ContentProfile.GENERIC
    # 同一内容、两种容器、两个 profile：这就是债本身
    assert (
        manifests["pdf"].document.content_profile
        is not manifests["docx"].document.content_profile
    )

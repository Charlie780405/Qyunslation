"""PLAN-042：611-2期实样金标（仓库外路径）。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from qyunslation.structure.models import ContentProfile, ObjectType
from qyunslation.structure.regulatory_entities import (
    lookup_controlled,
    normalize_phase_label,
    rewrite_embedded_phase,
)
from qyunslation.structure.scan_pdf import PdfStructureScanner
from qyunslation.structure.table_translate import translate_table_blocks
from qyunslation.structure.models import (
    BoundingBox,
    TranslatableBlock,
    TranslationPolicy,
)

SAMPLE = Path(os.environ.get("QYUNSLATION_PLAN042_SAMPLE") or "")

pytestmark = pytest.mark.skipif(
    not SAMPLE.is_file(),
    reason="QYUNSLATION_PLAN042_SAMPLE missing",
)


def test_plan042_real_sample_detects_regulatory_tables():
    manifest = PdfStructureScanner().scan(SAMPLE)
    tables = [o for o in manifest.objects if o.type is ObjectType.TABLE]
    assert manifest.document.content_profile is ContentProfile.REGULATORY
    assert len(tables) == 12
    by_page: dict[int, int] = {}
    for table in tables:
        page = int(str(table.canvas_id).split(":")[-1])
        by_page[page] = by_page.get(page, 0) + 1
    assert by_page == {1: 4, 2: 1, 3: 2, 4: 1, 5: 4}


def test_plan042_real_sample_chain_is_detected_not_missing():
    """截图缺陷来自「检出后硬失败回退 BabelDOC」，不是未检出。"""
    manifest = PdfStructureScanner().scan(SAMPLE)
    tables = [o for o in manifest.objects if o.type is ObjectType.TABLE]
    assert tables, "expected captionless regulatory tables"
    assert all((t.translatable_blocks or []) for t in tables)


def test_phase_normalize_does_not_swallow_long_title():
    title = (
        "一项在慢性鼻窦炎伴鼻息肉（CRSwNP）受试者中评估611 的 "
        "有效性与安全性的多中心、随机、双盲、安慰剂对照II 期 临床研究"
    )
    assert normalize_phase_label(title) == title
    rewritten = rewrite_embedded_phase(title)
    assert "Phase II" in rewritten
    assert "CRSwNP" in rewritten
    assert "611" in rewritten


def test_3sbio_controlled_skips_digit_drift():
    blocks = [
        TranslatableBlock(
            block_id="org",
            source_text="三生国健药业（上海）股份有限公司",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            row_index=0,
            column_index=1,
            bbox=BoundingBox(x0=0, y0=0, x1=200, y1=20),
        )
    ]

    def boom(_payloads):
        raise AssertionError("must use controlled lookup")

    out = translate_table_blocks(blocks, boom)
    assert "3SBio" in out["org"]
    assert lookup_controlled(blocks[0].source_text)

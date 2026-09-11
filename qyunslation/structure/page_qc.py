# SPDX-License-Identifier: MPL-2.0
"""PLAN-042f：全文级字号与中文残留门（不限表格链）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
_WORD_SPLIT = re.compile(r"\b[A-Za-z]{1,3}\s+[A-Za-z]{2,}\b")

QC_PAGE_CJK_RESIDUE = "PAGE_CJK_RESIDUE"
QC_PAGE_FONT_FLOOR = "PAGE_FONT_FLOOR"
QC_WORD_SPLIT = "WORD_SPLIT"


@dataclass
class PageQc:
    page_index: int
    cjk_chars: int = 0
    latin_words: int = 0
    spans_below_pt: int = 0
    word_split_hits: list[str] = field(default_factory=list)
    qc: list[str] = field(default_factory=list)

    def failed(self) -> bool:
        return bool(self.qc)


def scan_page_text_qc(
    page,
    *,
    expect_target_lang: str = "en",
    min_font_pt: float = 7.0,
    max_cjk_when_en: int = 0,
) -> PageQc:
    """扫描单页文本层：CJK 残留、字号下限、疑似词内断裂。"""
    qc = PageQc(page_index=int(getattr(page, "number", 0) or 0))
    try:
        data = page.get_text("dict")
    except Exception:
        return qc
    blob_parts: list[str] = []
    for block in data.get("blocks") or []:
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                text = span.get("text") or ""
                size = float(span.get("size") or 0)
                blob_parts.append(text)
                if text.strip() and size + 1e-6 < min_font_pt:
                    qc.spans_below_pt += 1
    blob = "".join(blob_parts)
    qc.cjk_chars = len(_CJK.findall(blob))
    qc.latin_words = len(_LATIN_WORD.findall(blob))
    # 词内断裂：短拉丁片 + 空格 + 拉丁续（启发式，供夹具）
    for m in _WORD_SPLIT.finditer(blob):
        hit = m.group(0)
        # 过滤正常短词（a / an / of / to）
        left = hit.split()[0].casefold()
        if left in {"a", "an", "of", "to", "in", "on", "or", "and", "the", "for"}:
            continue
        qc.word_split_hits.append(hit)
    if expect_target_lang.startswith("en") and qc.cjk_chars > max_cjk_when_en:
        qc.qc.append(QC_PAGE_CJK_RESIDUE)
    if qc.spans_below_pt:
        qc.qc.append(QC_PAGE_FONT_FLOOR)
    if qc.word_split_hits:
        qc.qc.append(QC_WORD_SPLIT)
    return qc


def assert_page_qc_clean(result: PageQc, *, allow_font: bool = False) -> None:
    codes = list(result.qc)
    if allow_font:
        codes = [c for c in codes if c != QC_PAGE_FONT_FLOOR]
    if codes:
        raise AssertionError(f"PAGE_QC_HARD:{codes}")

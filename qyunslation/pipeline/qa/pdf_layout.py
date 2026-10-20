# SPDX-License-Identifier: MPL-2.0
"""PLAN-080f：译后 PDF 的段落级漏译、字体种类、装饰线检查（只出警告，不阻断交付）。

现有 ``UNTRANSLATED_BODY`` / ``LATIN_RESIDUE`` 看的是全文英文行占比，样本里个别整段没译（占比很低）
完全没有信号。这里直接读源与译文两份 PDF：

* ``UNTRANSLATED_PARAGRAPH``：译文里有整段外文，且与源文同页逐字相同（"应译而原样保留"），
  并且它不是有名有据的保留（人名、职务、机构、网址、参考文献区、重复页眉页脚）。
* ``REFERENCE_ENTRIES_CHANGED``：源文里的参考文献（引文条目或一堆引文的段落）在译文同页不再逐字存在，
  也就是被翻译或改写了；参考文献应当原样保留。
* ``FONT_FAMILY_SPRAWL``：某页译文用了太多种字体（族 + 粗/斜体计一种，≥7 种且比源文该页多 2 种以上）。
* ``DECORATION_DANGLING``：还有下划线等装饰线没有跟上译文（过长、悬空或位置不对），判断与
  ``structure.decoration_realign`` 共用同一套逻辑。

开关 ``QYUNSLATION_LAYOUT_QA``（默认 off）。严重度一律是 warning（D4：基线稳定前不阻断）。
任何异常都返回空列表：QA 不能因为这一步自己出错而失败。
"""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from qyunslation.pipeline.qa import locate
from qyunslation.pipeline.qa.engine import QaFinding

MODE_ENV = "QYUNSLATION_LAYOUT_QA"

MIN_CHARS = 80            # 去空白后至少这么长才算"段落"
MIN_WORDS = 12
MIN_LOWER_WORD_SHARE = 0.4  # 小写开头的词占比：排除全大写缩写、名单、表头
HEADER_REPEAT_PAGES = 3     # 同一文字出现在这么多页以上，视为页眉页脚
FONT_FAMILIES_FLAG = 7      # 一页出现这么多种字体（族+粗斜体）才可能被标记
FONT_FAMILIES_OVER_SOURCE = 2
FONT_MIN_CHARS = 20         # 一个字体族在该页至少有这么多字符才计入
FONT_MIN_SIZE = 7.0

_CJK = re.compile(r"[一-鿿]")
_URL_OR_EMAIL = re.compile(r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def layout_qa_mode() -> str:
    value = (os.environ.get(MODE_ENV) or "off").strip().lower()
    return "on" if value in {"on", "1", "true", "yes"} else "off"


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _family(font_name: str) -> str:
    """字体的区分单位：族名 + 粗体 + 斜体。同一族的粗体、斜体在版面上就是另一种字形。"""
    from qyunslation.structure.font_style import infer_bold, infer_italic

    name = re.sub(r"^[A-Z]{6}\+", "", font_name or "")
    base = re.split(r"[-,]", name, maxsplit=1)[0]
    return base + ("/B" if infer_bold(name) else "") + ("/I" if infer_italic(name) else "")


def _text_blocks(page: Any) -> list[str]:
    return [str(b[4]) for b in page.get_text("blocks") if len(b) >= 7 and b[6] == 0 and str(b[4]).strip()]


def _is_candidate(text: str) -> bool:
    plain = _URL_OR_EMAIL.sub(" ", text)
    if _CJK.search(plain) or len(_compact(plain)) < MIN_CHARS:
        return False
    words = _WORD.findall(plain)
    if len(words) < MIN_WORDS:
        return False
    lower = sum(1 for w in words if w[0].islower())
    return lower / len(words) >= MIN_LOWER_WORD_SHARE


def untranslated_paragraphs(src: Any, out: Any) -> list[tuple[int, str]]:
    """[(页码, 段落节选)]：译文里与源文同页逐字相同、也不属于有名有据保留的整段外文。"""
    from qyunslation.structure.babeldoc_policy import ReferencePreserveGate
    from qyunslation.structure.entity_preserve import preserve_reason

    comparable = len(src) == len(out)
    src_compact = [_compact(page.get_text("text") or "") for page in src] if comparable else []
    blocks = [_text_blocks(page) for page in out]
    repeats = Counter(_compact(b) for page_blocks in blocks for b in set(page_blocks))
    gate = ReferencePreserveGate()
    hits: list[tuple[int, str]] = []
    for index, page_blocks in enumerate(blocks):
        for text in page_blocks:
            in_references = gate.should_preserve(text)  # 顺序推进参考文献区状态
            if in_references or not _is_candidate(text):
                continue
            compact = _compact(text)
            if repeats[compact] >= HEADER_REPEAT_PAGES:
                continue
            if preserve_reason(text) is not None:
                continue
            if comparable and compact not in src_compact[index]:
                continue
            hits.append((index + 1, locate.snippet(text, 120)))
    return hits


def changed_reference_blocks(src: Any, out: Any) -> list[tuple[int, str]]:
    """[(页码, 节选)]：源文里的引文条目/引文段落，在译文同页没有逐字保留。需要页数一致才能比较。"""
    from qyunslation.structure.references import is_citation_block, is_citation_entry

    if len(src) != len(out):
        return []
    hits: list[tuple[int, str]] = []
    for index in range(len(src)):
        out_compact = _compact(out[index].get_text("text") or "")
        for text in _text_blocks(src[index]):
            if len(_compact(text)) < MIN_CHARS or not (is_citation_entry(text) or is_citation_block(text)):
                continue
            if _compact(text) not in out_compact:
                hits.append((index + 1, locate.snippet(text, 120)))
    return hits


def _page_families(page: Any) -> set[str]:
    counts: Counter[str] = Counter()
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if text and span["size"] >= FONT_MIN_SIZE:
                    counts[_family(span["font"])] += len(text)
    return {family for family, n in counts.items() if n >= FONT_MIN_CHARS}


def font_sprawl_pages(src: Any, out: Any) -> list[tuple[int, int, int]]:
    """[(页码, 译文字体族数, 源文字体族数)]，只列出明显比源文多的页。"""
    pages = []
    for index in range(min(len(src), len(out))):
        out_n, src_n = len(_page_families(out[index])), len(_page_families(src[index]))
        if out_n >= FONT_FAMILIES_FLAG and out_n > src_n + FONT_FAMILIES_OVER_SOURCE:
            pages.append((index + 1, out_n, src_n))
    return pages


def dangling_decoration_pages(src: Any, out: Any) -> list[tuple[int, int]]:
    """[(页码, 还没跟上译文的装饰线数)]。"""
    from qyunslation.structure.decoration_realign import plan_page

    pages = []
    for index in range(min(len(src), len(out))):
        actions, _grid = plan_page(src[index], out[index])
        pending = sum(1 for action, _old, _new in actions if action != "keep")
        if pending:
            pages.append((index + 1, pending))
    return pages


def check_output_layout(source_path: Path, output_path: Path, *, output_kind: str = "mono") -> list[QaFinding]:
    """对一份译文 PDF 做三项检查；关闭、无法读取或出错时返回空列表。"""
    if layout_qa_mode() != "on":
        return []
    try:
        import pymupdf
    except ImportError:
        return []
    findings: list[QaFinding] = []
    try:
        src = pymupdf.open(str(source_path))
        out = pymupdf.open(str(output_path))
    except Exception:  # noqa: BLE001
        return []
    try:
        # 字体和装饰线要把源页与译文页一一配对；页数不一致时配对不可靠，只做不依赖配对的漏译检查
        checks = (
            (_check_untranslated, _check_references, _check_fonts, _check_decorations)
            if len(src) == len(out)
            else (_check_untranslated,)
        )
        for check in checks:
            try:
                finding = check(src, out, output_kind)
            except Exception:  # noqa: BLE001 — 某一项出错不影响其他项
                finding = None
            if finding is not None:
                findings.append(finding)
    finally:
        src.close()
        out.close()
    return findings


def _check_untranslated(src: Any, out: Any, output_kind: str) -> QaFinding | None:
    hits = untranslated_paragraphs(src, out)
    if not hits:
        return None
    pages = sorted({page for page, _ in hits})
    return QaFinding(
        category="integrity",
        severity="warning",
        code="UNTRANSLATED_PARAGRAPH",
        message=f"译文中有 {len(hits)} 个整段仍是外文，且与源文同页逐字相同",
        evidence={"output_kind": output_kind, "count": len(hits), "pages": pages[:20]},
        location=locate.location(
            [locate.page_anchor("translated", page, "整段仍为外文", text) for page, text in hits[: locate.MAX_ANCHORS]]
        ),
    )


def _check_references(src: Any, out: Any, output_kind: str) -> QaFinding | None:
    hits = changed_reference_blocks(src, out)
    if not hits:
        return None
    pages = sorted({page for page, _ in hits})
    return QaFinding(
        category="integrity",
        severity="warning",
        code="REFERENCE_ENTRIES_CHANGED",
        message=f"{len(hits)} 处参考文献在译文中不再与源文一致（可能被翻译或改写）",
        evidence={"output_kind": output_kind, "count": len(hits), "pages": pages[:20]},
        location=locate.location(
            [locate.page_anchor("translated", page, "参考文献与源文不一致", text) for page, text in hits[: locate.MAX_ANCHORS]]
        ),
    )


def _check_fonts(src: Any, out: Any, output_kind: str) -> QaFinding | None:
    pages = font_sprawl_pages(src, out)
    if not pages:
        return None
    worst = max(n for _page, n, _src in pages)
    return QaFinding(
        category="layout",
        severity="warning",
        code="FONT_FAMILY_SPRAWL",
        message=f"{len(pages)} 页译文使用的字体族明显多于源文（最多 {worst} 种）",
        evidence={"output_kind": output_kind, "pages": [p for p, _n, _s in pages][:20], "max_families": worst},
        location=locate.location(
            [locate.page_anchor("translated", p, f"本页用了 {n} 种字体族（源文 {s} 种）") for p, n, s in pages[: locate.MAX_ANCHORS]]
        ),
    )


def _check_decorations(src: Any, out: Any, output_kind: str) -> QaFinding | None:
    pages = dangling_decoration_pages(src, out)
    if not pages:
        return None
    total = sum(n for _p, n in pages)
    return QaFinding(
        category="layout",
        severity="warning",
        code="DECORATION_DANGLING",
        message=f"{total} 条下划线等装饰线没有跟上译文（过长、悬空或位置不对）",
        evidence={"output_kind": output_kind, "count": total, "pages": [p for p, _n in pages][:20]},
        location=locate.location(
            [locate.page_anchor("translated", p, f"本页 {n} 条装饰线与译文文字不对应") for p, n in pages[: locate.MAX_ANCHORS]]
        ),
    )

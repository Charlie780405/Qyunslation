# SPDX-License-Identifier: MPL-2.0
"""PLAN-071e：从源/译文 PDF 提取确定性 QA 的真实输入。

文本规则为纯函数（可单测）；PDF 读取依赖 PyMuPDF，缺失时返回 None 让调用方
记录 ``QA_INPUT_UNAVAILABLE`` 而不是静默通过。
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qyunslation.pipeline.qa import locate
from qyunslation.pipeline.qa.engine import QaFinding
from qyunslation.structure.frontmatter import AFFILIATION, AUTHOR, classify_frontmatter_text
from qyunslation.structure.text_sanitize import (
    _CONTROL_RE,
    _MOJIBAKE_RE,
    artifact_evidence,
    is_decorative_unmapped_inherited,
    detect_text_artifacts,
    space_map_evidence,
    symbol_glyph_evidence,
    visible_codepoint_excerpt,
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s)>\]，。；]+")
IND_RE = re.compile(r"\b(?:PIND|IND|NCT)\s?-?\d{5,8}\b")
DOSE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:mg/kg|mg|mL|ml|μg|µg|mcg|kg|IU|%)(?!\w)"
)
FREQ_RE = re.compile(r"\bQ\d+W\b|\bBID\b|\bQD\b|\bTID\b")
ORDINAL_ARTIFACT_RE = re.compile(r"\^\{(?:st|nd|rd|th)\}")
LATIN_RUN_RE = re.compile(r"(?:\b[A-Za-z][A-Za-z'-]{2,}\b[ ,;:]+){5,}\b[A-Za-z][A-Za-z'-]*\b")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

BLOCKER_LITERALS = {"email", "ind"}


@dataclass
class PdfFacts:
    page_count: int
    text: str
    image_hashes: set[str] = field(default_factory=set)
    pages: list[str] = field(default_factory=list)  # text of each page (index 0 = page 1)
    first_page_image_hashes: set[str] = field(default_factory=set)


def strip_reference_section(text: str) -> str:
    """去掉参考文献区（标题行起，到附录/致谢等分节标题前）。

    参考文献整区保持原文、不翻译（PLAN-033h）；其中的网址、DOI、英文行不属于「译文漏译/网址被改写」，
    QA 不该为它们报警，更不能阻断。只认独立标题行，与 structure.references 同一套规则。
    """
    from qyunslation.structure.references import HEADING_RE, SECTION_BREAK_RE

    kept: list[str] = []
    in_refs = False
    for line in (text or "").splitlines():
        if HEADING_RE.match(line):
            in_refs = True
            continue
        if in_refs and SECTION_BREAK_RE.match(line):
            in_refs = False
        if not in_refs:
            kept.append(line)
    return "\n".join(kept)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# PDF 文本层常在网址的点、斜杠后塞零宽空格（便于折行），肉眼不可见但字符串不相等。
_INVISIBLE_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")


def _strip_invisible(text: str) -> str:
    return _INVISIBLE_RE.sub("", text or "")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", _strip_invisible(text))


_LITERAL_PATTERNS: dict[str, tuple[re.Pattern[str], Any]] = {
    "email": (EMAIL_RE, lambda raw: raw.lower()),
    "url": (URL_RE, lambda raw: raw.rstrip(".,;")),
    "ind": (IND_RE, lambda raw: re.sub(r"[\s-]", "", raw).upper()),
    "dose": (DOSE_RE, lambda raw: re.sub(r"\s", "", raw).lower()),
    "freq": (FREQ_RE, lambda raw: raw.upper()),
}


def iter_literal_matches(text: str, kind: str):
    """Yield (normalised value, (start, end)) for every protected literal of ``kind``."""
    pattern, normalise = _LITERAL_PATTERNS[kind]
    for match in pattern.finditer(_strip_invisible(text)):
        yield normalise(match.group(0)), match.span()


def extract_protected_literals(text: str) -> dict[str, set[str]]:
    return {kind: {value for value, _span in iter_literal_matches(text, kind)} for kind in _LITERAL_PATTERNS}


def _literal_anchors(
    kind: str, missing: list[str], source_text: str, source_pages: list[str] | None
) -> list[dict[str, Any]]:
    segments = locate.segments_from_pages(source_pages) if source_pages else locate.segments_from_text(source_text)
    wanted = set(missing)
    anchors: list[dict[str, Any]] = []
    for segment in segments:
        clean = _strip_invisible(segment.text)
        for value, (start, end) in iter_literal_matches(segment.text, kind):
            if value in wanted:
                anchors.append(
                    locate.anchor("source", segment, value, locate.excerpt(clean, start, end))
                )
                wanted.discard(value)  # one place per value is enough to go and look
        if len(anchors) >= locate.MAX_ANCHORS or not wanted:
            break
    return anchors


# ---- equivalent writings (PLAN-078b b9 / D2) --------------------------------------------------------
# A Chinese translation of "300 mg" or "Q2W" is often written 300毫克 / 每2周. The value must still be
# there with the *same number* and an *equivalent unit or schedule*; anything else is still flagged.

_DOSE_UNIT_ALIASES: dict[str, tuple[str, ...]] = {
    "mg": ("mg", "毫克"),
    "g": ("g", "克"),
    "kg": ("kg", "千克", "公斤"),
    "ml": ("ml", "毫升"),
    "mcg": ("mcg", "μg", "µg", "微克"),
    "μg": ("mcg", "μg", "µg", "微克"),
    "µg": ("mcg", "μg", "µg", "微克"),
    "iu": ("iu", "国际单位"),
    "mg/kg": ("mg/kg", "毫克/千克", "毫克/公斤", "毫克每千克", "毫克每公斤"),
    "%": ("%",),
}
_ZH_NUMERAL = {"1": "一", "2": "二两", "3": "三", "4": "四", "5": "五", "6": "六", "8": "八", "10": "十", "12": "十二"}
_FREQ_PATTERNS: dict[str, tuple[str, ...]] = {
    "QD": (r"每[日天]一次", r"每[日天]1次", r"一[日天]一次", r"一[日天]1次", r"每[日天]给药一次"),
    "BID": (r"每[日天][两二2]次", r"一[日天][两二2]次"),
    "TID": (r"每[日天][三3]次", r"一[日天][三3]次"),
}


def _fold_for_match(text: str) -> str:
    import unicodedata

    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or "")).lower()


def _dose_present(value: str, translated_text: str) -> bool:
    compact = _fold_for_match(translated_text)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(.+)", value)
    if not match:
        return value in compact
    number, unit = match.group(1), match.group(2).lower()
    for alias in _DOSE_UNIT_ALIASES.get(unit, (unit,)):
        # the number must stand alone (300 is not part of 1300 or 300.5) and be followed by the unit
        if re.search(rf"(?<![\d.]){re.escape(number)}{re.escape(alias.lower())}", compact):
            return True
    return False


def _freq_present(value: str, translated_text: str) -> bool:
    compact = _fold_for_match(translated_text)
    token = value.lower()
    if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", compact):
        return True
    weekly = re.fullmatch(r"q(\d+)w", token)
    if weekly:
        n = weekly.group(1)
        zh = _ZH_NUMERAL.get(n, "")
        numerals = rf"(?:{n}" + (rf"|[{zh}]" if zh else "") + ")"
        return bool(re.search(rf"每(?:隔)?{numerals}周", compact))
    return any(re.search(pattern, compact) for pattern in _FREQ_PATTERNS.get(value.upper(), ()))


def _whole_urls(values: set[str]) -> set[str]:
    """丢掉被换行截断的网址碎片（https://、https://doi、另一条网址的前缀）。

    PDF 里一条网址常断成多行，逐行匹配会得到一堆前缀；它们不是独立网址，
    译文里只要完整网址在就不该报缺失。
    """
    hosted = {v for v in values if re.match(r"https?://[^/\s]+\.[A-Za-z]{2,}", v)}
    return {v for v in hosted if not any(o != v and o.startswith(v) for o in hosted)}


def check_protected_literals(
    source_text: str, translated_text: str, *, source_pages: list[str] | None = None
) -> list[QaFinding]:
    findings: list[QaFinding] = []
    translated_compact = _compact(translated_text).lower()
    translated_ind = re.sub(r"[\s-]", "", _strip_invisible(translated_text)).upper()
    for kind, values in extract_protected_literals(source_text).items():
        if kind == "url":
            values = _whole_urls(values)
        missing = []
        for value in sorted(values):
            if kind == "ind":
                present = value in translated_ind
            else:
                present = _compact(value).lower() in translated_compact
                if not present and kind == "dose":
                    present = _dose_present(value, translated_text)
                elif not present and kind == "freq":
                    present = _freq_present(value, translated_text)
            if not present:
                missing.append(value)
        if not missing:
            continue
        findings.append(
            QaFinding(
                category="clinical",
                severity="blocker" if kind in BLOCKER_LITERALS else "warning",
                code=f"LITERAL_MISSING_{kind.upper()}",
                message=f"原文受保护 {kind} 在译文中缺失或被改写：{', '.join(missing[:5])}",
                evidence={"kind": kind, "missing": missing[:20], "total_source": len(values)},
                location=locate.location(_literal_anchors(kind, missing, source_text, source_pages)),
            )
        )
    return findings


def _author_metadata_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in (text or "").splitlines()
        if line.strip() and classify_frontmatter_text(line).role == AUTHOR
    ]


def _preserved_frontmatter_terms(text: str) -> set[str]:
    """Exclude preserved English names and organizations from untranslated-text checks."""
    terms: set[str] = set()
    for line in (text or "").splitlines():
        if classify_frontmatter_text(line).role not in {AUTHOR, AFFILIATION}:
            continue
        value = line.strip()
        if value:
            terms.add(value)
            words = re.findall(r"[A-Za-z][A-Za-z'-]*", value)
            terms.update(" ".join(words[index : index + 3]) for index in range(len(words) - 2))
    return terms


def check_author_metadata(
    source_text: str, translated_text: str, *, source_pages: list[str] | None = None
) -> list[QaFinding]:
    """Author metadata is immutable; punctuation changes block publication."""
    authors = _author_metadata_lines(source_text)
    translated = _norm(translated_text)
    missing = [line for line in authors if _norm(line) not in translated]
    if not missing:
        return []
    return [
        QaFinding(
            category="integrity",
            severity="blocker",
            code="AUTHOR_METADATA_CHANGED",
            message="作者元数据缺失或被改写，必须与源文逐行一致",
            evidence={"missing": missing[:20], "total_source": len(authors)},
            location=locate.location(
                [
                    locate.anchor("source", seg, line[:60], locate.snippet(line))
                    for line in missing[:locate.MAX_ANCHORS]
                    for seg in locate.find_segments(
                        locate.segments_from_pages(source_pages) if source_pages else locate.segments_from_text(source_text),
                        lambda s, _line=line: _norm(_line) in _norm(s.text),
                        limit=1,
                    )
                ]
            ),
        )
    ]


def _residue_lines(text: str, protected: set[str] | None = None) -> tuple[list[str], int]:
    """(lines that look like untranslated English, number of non-empty lines)."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    protected = protected or set()
    hits: list[str] = []
    for line in lines:
        probe = line
        for token in protected:
            probe = probe.replace(token, " ")
        if LATIN_RUN_RE.search(probe) and not CJK_RE.search(probe):
            hits.append(line)
    return hits, len(lines)


def latin_residue_ratio(text: str, *, protected: set[str] | None = None) -> float:
    """含长英文串的行占非空行比例（译文目标为中文时用于疑似漏翻译）。"""
    hits, total = _residue_lines(text, protected)
    return len(hits) / total if total else 0.0


def _page_hits(pages: list[str] | None, predicate) -> list[tuple[int, str]]:
    return [(i, page) for i, page in enumerate(pages or [], start=1) if predicate(page)]


def _merge_families(parts: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {}
    for part in parts:
        for family, marks in part.items():
            merged.setdefault(family, set()).update(marks)
    return {family: sorted(marks)[:8] for family, marks in merged.items()}


def _encoding_findings(
    translated_text: str,
    translated_pages: list[str] | None,
    source_pages: list[str] | None,
    *,
    bilingual: bool = False,
) -> list[QaFinding]:
    """PLAN-079 D / PLAN-082 S4: garbled-text findings with space-glyph false-positive downgrade."""
    hits = [
        (number, artifact_evidence(page))
        for number, page in enumerate(translated_pages or [], start=1)
        if artifact_evidence(page)
    ]
    message = "译文包含不可打印字符或编码乱码，必须重新生成"
    if not hits:
        whole = artifact_evidence(translated_text)
        if space_map_evidence(translated_text):
            return [
                QaFinding(
                    category="integrity", severity="warning", code="TEXT_LAYER_SPACE_MAP",
                    message="译文文本层把空格字形映射成了控制字符；页面通常可读，复制时可能出现异常符号",
                    evidence={"detectors": whole, "pages": []},
                    location=locate.location([]),
                )
            ]
        return [
            QaFinding(
                category="integrity", severity="blocker", code="TEXT_ENCODING_ARTIFACT", message=message,
                evidence={"detectors": whole, "pages": []},
                location=locate.location([]),
            )
        ]
    comparable = bool(source_pages) and len(source_pages or []) == len(translated_pages or [])
    # Family-overlap downgrade stays opt-in ("1"). Default "auto" only downgrades the decorative-glyph case proven on
    # MG-K10: the source font maps a bullet/■ to U+0001, the translation keeps the same glyph (renders fine) but its
    # text layer shows U+FFFD. Allowed only when the page has no more unmapped marks than the source page did.
    mode = os.environ.get("QYUNSLATION_ENCODING_INHERITANCE", "auto").strip().casefold()
    inheritance = mode in {"1", "true", "on"}
    auto_inherit = comparable and mode in {"auto", ""}
    blocking: list[tuple[int, dict[str, list[str]]]] = []
    inherited: list[tuple[int, dict[str, list[str]]]] = []
    space_mapped: list[tuple[int, dict[str, list[str]]]] = []
    symbol_glyphs: list[tuple[int, dict[str, list[str]]]] = []
    pages = translated_pages or []
    for number, evidence in hits:
        page = pages[number - 1]
        if space_map_evidence(page):
            space_mapped.append((number, evidence))
            continue
        if symbol_glyph_evidence(page):
            symbol_glyphs.append((number, evidence))
            continue
        in_source = artifact_evidence(source_pages[number - 1]) if (comparable and inheritance) else {}
        decorative = auto_inherit and is_decorative_unmapped_inherited(
            source_pages[number - 1], page, copies=2 if bilingual else 1
        )
        (inherited if (set(in_source) & set(evidence)) or decorative else blocking).append((number, evidence))
    out: list[QaFinding] = []
    if blocking:
        out.append(
            QaFinding(
                category="integrity", severity="blocker", code="TEXT_ENCODING_ARTIFACT", message=message,
                evidence={
                    "detectors": _merge_families([e for _, e in blocking]),
                    "pages": [n for n, _ in blocking],
                    "source_compared": comparable,
                },
                location=locate.location(
                    [locate.page_anchor("translated", n, "乱码或不可打印字符", _artifact_excerpt(pages[n - 1])) for n, _ in blocking]
                ),
            )
        )
    if space_mapped:
        out.append(
            QaFinding(
                category="integrity", severity="warning", code="TEXT_LAYER_SPACE_MAP",
                message="译文文本层把空格字形映射成了控制字符；页面通常可读，复制时可能出现异常符号",
                evidence={
                    "detectors": _merge_families([e for _, e in space_mapped]),
                    "pages": [n for n, _ in space_mapped],
                },
                location=locate.location(
                    [locate.page_anchor("translated", n, "空格字形映射伪影", _artifact_excerpt(pages[n - 1])) for n, _ in space_mapped]
                ),
            )
        )
    if symbol_glyphs:
        out.append(
            QaFinding(
                category="integrity", severity="warning", code="TEXT_LAYER_SYMBOL_GLYPH",
                message="译文文本层里有单独的符号字形（项目符号、页眉分隔符）；页面能正常显示，只有复制文本时可能出现异常符号",
                evidence={
                    "detectors": _merge_families([e for _, e in symbol_glyphs]),
                    "pages": [n for n, _ in symbol_glyphs],
                },
                location=locate.location(
                    [locate.page_anchor("translated", n, "符号字形无文字映射", _artifact_excerpt(pages[n - 1])) for n, _ in symbol_glyphs]
                ),
            )
        )
    if inherited:
        out.append(
            QaFinding(
                category="integrity", severity="info", code="TEXT_ENCODING_INHERITED",
                message="译文中的异常字符在源文同一页也存在，多半来自源文本身",
                evidence={"detectors": _merge_families([e for _, e in inherited]), "pages": [n for n, _ in inherited]},
                location=locate.location(
                    [locate.page_anchor("translated", n, "源文同页也有异常字符", _artifact_excerpt(pages[n - 1])) for n, _ in inherited]
                ),
            )
        )
    return out


def _span_overlap_pairs(page) -> int:
    """Count span pairs whose intersection covers >35% of the smaller box."""
    try:
        blocks = page.get_text("dict").get("blocks") or []
    except Exception:
        return 0
    rects = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                text = str(span.get("text") or "").strip()
                if not text:
                    continue
                bbox = span.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
                if area <= 1.0:
                    continue
                rects.append((x0, y0, x1, y1, area))
    overlaps = 0
    for index, (ax0, ay0, ax1, ay1, aa) in enumerate(rects):
        for bx0, by0, bx1, by1, ba in rects[index + 1 :]:
            ix0, iy0 = max(ax0, bx0), max(ay0, by0)
            ix1, iy1 = min(ax1, bx1), min(ay1, by1)
            inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
            if inter <= 0:
                continue
            if inter / min(aa, ba) > 0.35:
                overlaps += 1
    return overlaps


def check_table_text_overlap(
    translated_path: Path,
    *,
    source_path: Path | None = None,
    min_pairs: int = 20,
) -> list[QaFinding]:
    """PLAN-082 S5: block when table pages show heavy overlapping text boxes."""
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except ImportError:
        try:
            import fitz  # type: ignore[import-not-found,no-redef]
        except ImportError:
            return []
    table_pages: set[int] = set()
    if source_path is not None and source_path.is_file():
        try:
            from qyunslation.structure.models import ObjectType
            from qyunslation.structure.scan_pdf import PdfStructureScanner

            manifest = PdfStructureScanner().scan(source_path)
            for obj in manifest.objects:
                if obj.type is not ObjectType.TABLE:
                    continue
                try:
                    page_no = int(str(obj.canvas_id).split(":")[-1])
                except Exception:
                    continue
                table_pages.add(page_no)
        except Exception:
            table_pages = set()
    try:
        doc = fitz.open(str(translated_path))
    except Exception:
        return []
    try:
        hot: list[tuple[int, int]] = []
        for index, page in enumerate(doc, start=1):
            if table_pages and index not in table_pages:
                continue
            pairs = _span_overlap_pairs(page)
            if pairs >= min_pairs:
                hot.append((index, pairs))
        if not hot:
            return []
        return [
            QaFinding(
                category="layout",
                severity="blocker",
                code="TABLE_TEXT_OVERLAP",
                message="译文表格区域文字框严重重叠，列对齐可能已损坏",
                evidence={
                    "pages": [n for n, _ in hot],
                    "overlap_pairs": {str(n): c for n, c in hot},
                    "threshold": min_pairs,
                },
                location=locate.location(
                    [
                        locate.page_anchor(
                            "translated",
                            n,
                            f"表格文字重叠（{c} 对）",
                        )
                        for n, c in hot[:5]
                    ]
                ),
            )
        ]
    finally:
        doc.close()


def _artifact_excerpt(page: str) -> str | None:
    for pattern in ("\ufffd",):
        at = page.find(pattern)
        if at >= 0:
            return visible_codepoint_excerpt(page, at, at + 1, radius=30)
    for regex in (_CONTROL_RE, _MOJIBAKE_RE):
        match = regex.search(page)
        if match:
            return visible_codepoint_excerpt(page, match.start(), match.end(), radius=30)
    return None


def _residue_anchors(pages: list[str] | None, protected: set[str]) -> list[dict[str, Any]]:
    scored: list[tuple[float, int, str]] = []
    for number, page in enumerate(pages or [], start=1):
        hits, total = _residue_lines(page, protected)
        if hits:
            scored.append((len(hits) / total, number, hits[0]))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        locate.page_anchor("translated", number, f"英文残留行约占本页 {ratio:.0%}", locate.snippet(first, 120))
        for ratio, number, first in scored[:5]
    ]


def check_translation_text(
    *,
    source_text: str,
    translated_text: str,
    target_is_chinese: bool = True,
    residue_warn: float = 0.35,
    residue_block: float = 0.8,
    source_pages: list[str] | None = None,
    translated_pages: list[str] | None = None,
    bilingual: bool = False,
) -> list[QaFinding]:
    findings: list[QaFinding] = []
    if not _norm(translated_text):
        return [
            QaFinding(
                category="integrity",
                severity="blocker",
                code="EMPTY_TRANSLATION",
                message="译文为空",
            )
        ]
    if ORDINAL_ARTIFACT_RE.search(translated_text):
        findings.append(
            QaFinding(
                category="clinical",
                severity="blocker",
                code="ORDINAL_ARTIFACT",
                message="出现序数上标伪影（如 ^{th}）",
                location=locate.location(
                    [
                        locate.page_anchor(
                            "translated", number, "序数上标伪影",
                            locate.excerpt(page, m.start(), m.end(), radius=30),
                        )
                        for number, page in _page_hits(translated_pages, ORDINAL_ARTIFACT_RE.search)[:5]
                        for m in [ORDINAL_ARTIFACT_RE.search(page)]
                    ]
                ),
            )
        )
    if "Fallback to simple translation" in translated_text:
        findings.append(
            QaFinding(
                category="integrity",
                severity="warning",
                code="FALLBACK_PRESENT",
                message="存在 fallback 段落，需人工确认",
                location=locate.location(
                    [
                        locate.page_anchor("translated", number, "回退翻译段落")
                        for number, _ in _page_hits(translated_pages, lambda p: "Fallback to simple translation" in p)[:5]
                    ]
                ),
            )
        )
    for code in detect_text_artifacts(translated_text):
        if code == "TEXT_ENCODING_ARTIFACT":
            findings.extend(_encoding_findings(translated_text, translated_pages, source_pages, bilingual=bilingual))
            continue
        findings.append(
            QaFinding(
                category="integrity",
                severity="blocker",
                code=code,
                message="译文包含中间标记残留，必须重新清洗并生成",
                location=locate.location(
                    [
                        locate.page_anchor("translated", number, "内部标记残留")
                        for number, _ in _page_hits(translated_pages, lambda p, c=code: c in detect_text_artifacts(p))[:5]
                    ]
                ),
            )
        )
    # 参考文献区保持原文：网址/英文行不参与「受保护字面量」与「英文残留」检查。
    findings.extend(
        check_protected_literals(strip_reference_section(source_text), translated_text, source_pages=source_pages)
    )
    findings.extend(check_author_metadata(source_text, translated_text, source_pages=source_pages))

    if target_is_chinese:
        protected = set().union(
            *(extract_protected_literals(source_text).values())
        )
        protected.update(_preserved_frontmatter_terms(source_text))
        ratio = latin_residue_ratio(strip_reference_section(translated_text), protected=protected)
        if ratio >= residue_block:
            findings.append(
                QaFinding(
                    category="integrity",
                    severity="blocker",
                    code="UNTRANSLATED_BODY",
                    message=f"译文大部分行仍为英文（{ratio:.0%}），疑似未翻译",
                    evidence={"latin_line_ratio": round(ratio, 3)},
                    location=locate.location(_residue_anchors(translated_pages, protected)),
                )
            )
        elif ratio >= residue_warn:
            findings.append(
                QaFinding(
                    category="integrity",
                    severity="warning",
                    code="LATIN_RESIDUE",
                    message=f"译文含较多英文残留行（{ratio:.0%}），需人工复核",
                    evidence={"latin_line_ratio": round(ratio, 3)},
                    location=locate.location(_residue_anchors(translated_pages, protected)),
                )
            )
    return findings


def read_pdf_facts(path: Path) -> PdfFacts | None:
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except ImportError:
        try:
            import fitz  # type: ignore[import-not-found,no-redef]
        except ImportError:
            return None
    try:
        doc = fitz.open(str(path))
    except Exception:
        return None
    try:
        texts: list[str] = []
        hashes: set[str] = set()
        first: set[str] = set()
        # Drop TEXT_USE_CID_FOR_UNKNOWN_UNICODE so blank spacing glyphs missing from
        # ToUnicode are not surfaced as U+0003 (PLAN-082 S4). Keep whitespace/ligatures/clip.
        try:
            import pymupdf as _fitz  # type: ignore[import-not-found]
            text_flags = (
                getattr(_fitz, "TEXT_PRESERVE_LIGATURES", 1)
                | getattr(_fitz, "TEXT_PRESERVE_WHITESPACE", 2)
                | getattr(_fitz, "TEXT_MEDIABOX_CLIP", 64)
            )
        except Exception:
            text_flags = 67
        for index, page in enumerate(doc):
            try:
                texts.append(page.get_text("text", flags=text_flags) or "")
            except TypeError:
                texts.append(page.get_text("text") or "")
            for img in page.get_images(full=True):
                try:
                    data = doc.extract_image(img[0]).get("image") or b""
                except Exception:
                    continue
                if not data:
                    continue
                digest = hashlib.sha256(data).hexdigest()
                hashes.add(digest)
                if index == 0:
                    first.add(digest)
        return PdfFacts(
            page_count=doc.page_count,
            text="\n".join(texts),
            image_hashes=hashes,
            first_page_image_hashes=first,
            pages=texts,
        )
    finally:
        doc.close()


def inspect_pdf_pair(
    *,
    source_path: Path,
    mono_path: Path | None,
    dual_path: Path | None,
    target_is_chinese: bool = True,
    facts_out: dict[str, PdfFacts] | None = None,
) -> tuple[list[QaFinding], dict[str, Any]]:
    """返回 (findings, 取证摘要)。无法读取任何输入时给出 warning，不静默通过。"""
    summary: dict[str, Any] = {}
    source = read_pdf_facts(source_path)
    outputs: dict[str, PdfFacts] = {}
    if mono_path is not None:
        mono = read_pdf_facts(mono_path)
        if mono is not None:
            outputs["mono"] = mono
    if dual_path is not None:
        dual = read_pdf_facts(dual_path)
        if dual is not None:
            outputs["dual"] = dual
    if source is None or not outputs:
        summary["inputs"] = "unavailable"
        return (
            [
                QaFinding(
                    category="integrity",
                    severity="warning",
                    code="QA_INPUT_UNAVAILABLE",
                    message="无法读取源/译文 PDF，确定性 QA 未能检查文本与版式",
                )
            ],
            summary,
        )
    if facts_out is not None:
        facts_out["source"] = source
        facts_out.update(outputs)
        facts_out["translated"] = outputs.get("mono") or outputs["dual"]
    findings: list[QaFinding] = []
    for output_kind, translated in outputs.items():
        current = check_translation_text(
            source_text=source.text,
            translated_text=translated.text,
            # A bilingual PDF intentionally retains source-language body text.
            target_is_chinese=target_is_chinese and output_kind == "mono",
            source_pages=source.pages,
            translated_pages=translated.pages,
            bilingual=output_kind == "dual",
        )
        for finding in current:
            finding.evidence.setdefault("output_kind", output_kind)
            for item in finding.location.get("anchors", []):
                if item.get("side") == "translated":
                    item.setdefault("output_kind", output_kind)
        findings.extend(current)
        if output_kind == "mono" and target_is_chinese and mono_path is not None:
            # PLAN-080f：段落级漏译、字体种类、装饰线（默认关闭，只出警告）
            from qyunslation.pipeline.qa.pdf_layout import check_output_layout

            findings.extend(check_output_layout(source_path, mono_path, output_kind=output_kind))
            # PLAN-082 S5：表区文字框重叠（串格/表头糊在一起）
            for finding in check_table_text_overlap(mono_path, source_path=source_path):
                finding.evidence.setdefault("output_kind", output_kind)
                findings.append(finding)
        if source.page_count != translated.page_count:
            findings.append(
                QaFinding(
                    category="layout",
                    severity="blocker",
                    code="PAGE_COUNT_MISMATCH",
                    message=(
                        f"页数不一致 source={source.page_count} "
                        f"{output_kind}={translated.page_count}"
                    ),
                    evidence={"output_kind": output_kind},
                )
            )
        if source.first_page_image_hashes and not (
            source.first_page_image_hashes & translated.image_hashes
        ):
            findings.append(
                QaFinding(
                    category="layout",
                    severity="blocker",
                    code="LOGO_MISSING",
                    message="源文件首页图片（疑似 Logo/印章）未在译文中原样保留",
                    evidence={
                        "source_first_page_images": len(source.first_page_image_hashes),
                        "output_kind": output_kind,
                    },
                    location=locate.location([locate.page_anchor("source", 1, "首页图片（疑似标识或印章）")]),
                )
            )
    translated = outputs.get("mono") or outputs["dual"]
    summary.update(
        source_pages=source.page_count,
        output_pages=translated.page_count,
        source_images=len(source.image_hashes),
        output_images=len(translated.image_hashes),
        compared="+".join(outputs),
        checked_outputs=list(outputs),
    )
    return findings, summary

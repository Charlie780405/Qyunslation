# SPDX-License-Identifier: MPL-2.0
"""PLAN-071e：从源/译文 PDF 提取确定性 QA 的真实输入。

文本规则为纯函数（可单测）；PDF 读取依赖 PyMuPDF，缺失时返回 None 让调用方
记录 ``QA_INPUT_UNAVAILABLE`` 而不是静默通过。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qyunslation.pipeline.qa import locate
from qyunslation.pipeline.qa.engine import QaFinding
from qyunslation.structure.frontmatter import AUTHOR, classify_frontmatter_text
from qyunslation.structure.text_sanitize import (
    _CONTROL_RE,
    _MOJIBAKE_RE,
    detect_text_artifacts,
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


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


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
    for match in pattern.finditer(text or ""):
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
        for value, (start, end) in iter_literal_matches(segment.text, kind):
            if value in wanted:
                anchors.append(
                    locate.anchor("source", segment, value, locate.excerpt(segment.text, start, end))
                )
                wanted.discard(value)  # one place per value is enough to go and look
        if len(anchors) >= locate.MAX_ANCHORS or not wanted:
            break
    return anchors


def check_protected_literals(
    source_text: str, translated_text: str, *, source_pages: list[str] | None = None
) -> list[QaFinding]:
    findings: list[QaFinding] = []
    translated_compact = _compact(translated_text).lower()
    translated_ind = re.sub(r"[\s-]", "", translated_text).upper()
    for kind, values in extract_protected_literals(source_text).items():
        missing = []
        for value in sorted(values):
            if kind == "ind":
                present = value in translated_ind
            else:
                present = _compact(value).lower() in translated_compact
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


def _artifact_excerpt(page: str) -> str | None:
    for pattern in ("\ufffd",):
        at = page.find(pattern)
        if at >= 0:
            return locate.excerpt(page, at, at + 1, radius=30)
    for regex in (_CONTROL_RE, _MOJIBAKE_RE):
        match = regex.search(page)
        if match:
            return locate.excerpt(page, match.start(), match.end(), radius=30)
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
        findings.append(
            QaFinding(
                category="integrity",
                severity="blocker",
                code=code,
                message=(
                    "译文包含中间标记残留，必须重新清洗并生成"
                    if code == "IL_MARKUP_LEAK"
                    else "译文包含不可打印字符或编码乱码，必须重新生成"
                ),
                location=locate.location(
                    [
                        locate.page_anchor(
                            "translated", number,
                            "内部标记残留" if code == "IL_MARKUP_LEAK" else "乱码或不可打印字符",
                            _artifact_excerpt(page) if code != "IL_MARKUP_LEAK" else None,
                        )
                        for number, page in _page_hits(translated_pages, lambda p, c=code: c in detect_text_artifacts(p))[:5]
                    ]
                ),
            )
        )
    findings.extend(check_protected_literals(source_text, translated_text, source_pages=source_pages))
    findings.extend(check_author_metadata(source_text, translated_text, source_pages=source_pages))

    if target_is_chinese:
        protected = set().union(
            *(extract_protected_literals(source_text).values())
        )
        ratio = latin_residue_ratio(translated_text, protected=protected)
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
        for index, page in enumerate(doc):
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
        )
        for finding in current:
            finding.evidence.setdefault("output_kind", output_kind)
            for item in finding.location.get("anchors", []):
                if item.get("side") == "translated":
                    item.setdefault("output_kind", output_kind)
        findings.extend(current)
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

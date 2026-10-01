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

from qyunslation.pipeline.qa.engine import QaFinding

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
    first_page_image_hashes: set[str] = field(default_factory=set)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def extract_protected_literals(text: str) -> dict[str, set[str]]:
    return {
        "email": {m.group(0).lower() for m in EMAIL_RE.finditer(text)},
        "url": {m.group(0).rstrip(".,;") for m in URL_RE.finditer(text)},
        "ind": {re.sub(r"[\s-]", "", m.group(0)).upper() for m in IND_RE.finditer(text)},
        "dose": {re.sub(r"\s", "", m.group(0)).lower() for m in DOSE_RE.finditer(text)},
        "freq": {m.group(0).upper() for m in FREQ_RE.finditer(text)},
    }


def check_protected_literals(
    source_text: str, translated_text: str
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
            )
        )
    return findings


def latin_residue_ratio(text: str, *, protected: set[str] | None = None) -> float:
    """含长英文串的行占非空行比例（译文目标为中文时用于疑似漏翻译）。"""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return 0.0
    protected = protected or set()
    hit = 0
    for line in lines:
        probe = line
        for token in protected:
            probe = probe.replace(token, " ")
        if LATIN_RUN_RE.search(probe) and not CJK_RE.search(probe):
            hit += 1
    return hit / len(lines)


def check_translation_text(
    *,
    source_text: str,
    translated_text: str,
    target_is_chinese: bool = True,
    residue_warn: float = 0.35,
    residue_block: float = 0.8,
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
            )
        )
    if "Fallback to simple translation" in translated_text:
        findings.append(
            QaFinding(
                category="integrity",
                severity="warning",
                code="FALLBACK_PRESENT",
                message="存在 fallback 段落，需人工确认",
            )
        )
    findings.extend(check_protected_literals(source_text, translated_text))

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
    translated_path = mono_path or dual_path
    translated = read_pdf_facts(translated_path) if translated_path else None
    if source is None or translated is None:
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
        facts_out["translated"] = translated
    findings = check_translation_text(
        source_text=source.text,
        translated_text=translated.text,
        target_is_chinese=target_is_chinese,
    )
    summary.update(
        source_pages=source.page_count,
        output_pages=translated.page_count,
        source_images=len(source.image_hashes),
        output_images=len(translated.image_hashes),
        compared="mono" if mono_path else "dual",
    )
    if mono_path is not None and source.page_count != translated.page_count:
        findings.append(
            QaFinding(
                category="layout",
                severity="blocker",
                code="PAGE_COUNT_MISMATCH",
                message=f"页数不一致 source={source.page_count} output={translated.page_count}",
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
                evidence={"source_first_page_images": len(source.first_page_image_hashes)},
            )
        )
    return findings, summary

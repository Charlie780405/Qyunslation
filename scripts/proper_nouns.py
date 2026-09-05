#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""专名保护表：人工表 + 自动 identity harvest（PLAN-010d）。"""
from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "glossaries" / "proper-nouns.csv"
AUTO = ROOT / "glossaries" / "auto-proper-nouns.csv"

PATTERNS = (
    re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b"),  # GenScend / MedImmune
    re.compile(r"\b[\w.&'\- ]{2,40}?(?:Co\.,? ?Ltd\.|Inc\.|LLC|GmbH|PLC)\b"),
    re.compile(r"\b[A-Z]{3,6}\b"),  # IQVIA / MSHA
    re.compile(r"\b\w+(?:®|™)"),
)

STOPWORDS = {
    "FDA",
    "PIND",
    "CFR",
    "IND",
    "NDA",
    "BLA",
    "USA",
    "PDF",
    "OCR",
    "EASI",
    "IGA",
    "DLQI",
    "CDER",
    "ENCLOSURE",
    "MEETING",
}


def _read_sources(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    out: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            src = (row.get("source") or "").strip()
            if src:
                out.add(src)
    return out


def harvest_from_text(text: str, *, exclude: set[str] | None = None) -> list[str]:
    """从纯文本抽取候选专名（identity）。"""
    skip = set(STOPWORDS)
    if exclude:
        skip |= exclude
    found: list[str] = []
    seen: set[str] = set()
    for pat in PATTERNS:
        for m in pat.finditer(text or ""):
            term = " ".join(m.group(0).split()).strip()
            if not term or term in skip or term in seen:
                continue
            if term.upper() in STOPWORDS:
                continue
            seen.add(term)
            found.append(term)
    return found


def harvest(pdf: Path) -> int:
    """扫 PDF 文本写 AUTO（identity 行）；跳过 MANUAL 已有 + STOPWORDS。返回写入条数。"""
    import pymupdf

    pdf = Path(pdf)
    manual = _read_sources(MANUAL)
    exclude = set(manual) | set(STOPWORDS)
    doc = pymupdf.open(pdf)
    blob = "\n".join((page.get_text() or "") for page in doc)
    doc.close()
    terms = harvest_from_text(blob, exclude=exclude)
    AUTO.parent.mkdir(parents=True, exist_ok=True)
    with AUTO.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "target", "tgt_lng"])
        for term in sorted(terms, key=str.lower):
            w.writerow([term, term, ""])
    logger.info("proper_nouns harvest %s → %s terms=%s", pdf, AUTO, len(terms))
    return len(terms)


def glossary_args(extra: list[Path] | None = None) -> str:
    """逗号串给 --glossaries：manual → auto → extra。"""
    paths: list[Path] = []
    if MANUAL.is_file():
        paths.append(MANUAL)
    if AUTO.is_file():
        paths.append(AUTO)
    for p in extra or []:
        pp = Path(p)
        if pp.is_file() and pp.resolve() not in {x.resolve() for x in paths}:
            paths.append(pp)
    return ",".join(str(p) for p in paths)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="专名 harvest / glossary 串")
    ap.add_argument("pdf", nargs="?", type=Path, help="PDF 路径（harvest）")
    ap.add_argument("--print-args", action="store_true", help="打印 --glossaries 串")
    ap.add_argument("--extra", action="append", type=Path, default=[])
    args = ap.parse_args()
    if args.pdf:
        harvest(args.pdf)
    if args.print_args or not args.pdf:
        print(glossary_args(args.extra or None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

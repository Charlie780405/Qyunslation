#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-074 / 075c：Dupilumab 真件只读回归（样本缺失则 exit 2 BLOCKED）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PDF = ROOT / "var/pipeline/runs/65ecd028-4a56-4b7d-b473-ae05494c7f4d/gen-1/input/01-LIT-2026-Dupilumab-CaseReport.pdf"
DEFAULT_DUAL = ROOT / (
    "var/translation-runs/d8faef9f-5f8a-41a1-a65b-e9a4fc551e06/"
    "65ecd028-4a56-4b7d-b473-ae05494c7f4d/generation-1/output/"
    "01-LIT-2026-Dupilumab-CaseReport.no_watermark.zh.dual.pdf"
)
DEFAULT_MANIFEST = ROOT / "var/pipeline/runs/65ecd028-4a56-4b7d-b473-ae05494c7f4d/gen-1/manifest.json"

REQUIRED_TERMS = {
    "Dupilumab",
    "vitiligo",
    "atopic dermatitis",
    "IL-4",
    "IL-13",
    "melanocyte",
}
FORBIDDEN_TERMS = {
    "Patricia Curtin",
    "New York Medical College",
    "ICU",
    "SPF 30+",
    "Curtin P.",
}


def _resolve(name: str, default: Path) -> Path | None:
    raw = os.environ.get(name, "").strip()
    path = Path(raw) if raw else default
    return path if path.is_file() else None


def _collect_source_text(node: object, out: list[str]) -> None:
    if isinstance(node, dict):
        text = str(node.get("source_text") or "").strip()
        if text:
            out.append(text)
        for value in node.values():
            _collect_source_text(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_source_text(item, out)


def _manifest_source(manifest: Path) -> str:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    chunks: list[str] = []
    _collect_source_text(data, chunks)
    return "\n".join(chunks)


def main() -> int:
    pdf = _resolve("PLAN074_GOLD_PDF", DEFAULT_PDF)
    dual = _resolve("PLAN074_GOLD_DUAL_PDF", DEFAULT_DUAL)
    manifest = _resolve("PLAN074_GOLD_MANIFEST", DEFAULT_MANIFEST)

    missing = [
        label
        for label, path in (
            ("PLAN074_GOLD_PDF", pdf),
            ("PLAN074_GOLD_DUAL_PDF", dual),
            ("PLAN074_GOLD_MANIFEST", manifest),
        )
        if path is None
    ]
    if missing:
        print(f"BLOCKED: missing live regression inputs: {', '.join(missing)}")
        return 2

    from qyunslation.pipeline.qa.pdf_inspect import inspect_pdf_pair, read_pdf_facts
    from qyunslation.workbench.term_extract import discover_term_occurrences

    pdf_facts = read_pdf_facts(pdf)
    source = pdf_facts.text if pdf_facts and pdf_facts.text.strip() else _manifest_source(manifest)
    rows = discover_term_occurrences(source, "度普利尤单抗；vitiligo；IL-4；IL-13；melanocyte")
    found = {row["source_term"] for row in rows}
    missing_terms = REQUIRED_TERMS - found
    forbidden_hits = found & FORBIDDEN_TERMS

    findings, _summary = inspect_pdf_pair(
        source_path=pdf,
        mono_path=None,
        dual_path=dual,
        target_is_chinese=True,
    )
    blockers = [
        {"code": f.code, "message": f.message, "severity": f.severity}
        for f in findings
        if f.severity == "blocker"
    ]

    report = {
        "pdf": str(pdf),
        "dual_pdf": str(dual),
        "terms_found": sorted(found),
        "missing_terms": sorted(missing_terms),
        "forbidden_hits": sorted(forbidden_hits),
        "qa_blockers": blockers,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if missing_terms or forbidden_hits:
        print("FAIL: term gold checks failed")
        return 1
    legacy_codes = {"IL_MARKUP_LEAK", "TEXT_ENCODING_ARTIFACT"}
    if blockers and all(item["code"] in legacy_codes for item in blockers):
        print(
            "BLOCKED: legacy dual PDF still has encoding artifacts; "
            "rerun translation with PLAN-074 pipeline for full QA PASS"
        )
        return 2
    if blockers:
        print("FAIL: live regression QA blockers remain")
        return 1
    print("PASS: live regression")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

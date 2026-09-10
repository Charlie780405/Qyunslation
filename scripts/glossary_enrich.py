#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-039d：从任务 glossary / 对照 CSV 挖候选 → staging。"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from qyunslation.glossary.governance import (
    GLOSSARIES_DIR,
    GlossaryEntry,
    build_merged_dict,
    is_junk_source,
    load_glossary_csv,
    normalize_source,
    write_glossary_csv,
)

STAGING_DIR = GLOSSARIES_DIR / "staging"
_CAMEL = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b")
_ACRONYM = re.compile(r"\b[A-Z]{2,8}\b")
_COMPANY = re.compile(
    r"\b[\w.&'\- ]{2,40}?(?:Co\.,? ?Ltd\.|Inc\.|LLC|GmbH|PLC|生物|医药|制药)\b"
)


def _load_pair_csv(path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = [x.lower() for x in (reader.fieldnames or [])]
        for row in reader:
            # support source/target, src/dst, original/translation
            src = (
                row.get("source")
                or row.get("src")
                or row.get("original")
                or row.get("en")
                or ""
            ).strip()
            tgt = (
                row.get("target")
                or row.get("dst")
                or row.get("translation")
                or row.get("zh")
                or ""
            ).strip()
            if not src and len(row) >= 2:
                vals = list(row.values())
                src, tgt = (vals[0] or "").strip(), (vals[1] or "").strip()
            if src and tgt:
                pairs.append((src, tgt))
    return pairs


def _candidate_entries(pairs: list[tuple[str, str]], existing: set[str]) -> list[GlossaryEntry]:
    out: list[GlossaryEntry] = []
    seen: set[str] = set()
    for src, tgt in pairs:
        if is_junk_source(src):
            continue
        # keep short-ish terms; skip long sentences
        if len(src) > 80:
            continue
        if " " in src and len(src.split()) > 8 and not _COMPANY.search(src):
            # allow multiword clinical terms up to 8 tokens
            if not (_CAMEL.search(src) or _ACRONYM.fullmatch(src.replace(" ", ""))):
                if len(src.split()) > 6:
                    continue
        key = normalize_source(src)
        if key in existing or key in seen:
            continue
        seen.add(key)
        out.append(
            GlossaryEntry(
                source=src,
                target=tgt,
                layer="clinical",
                domain="",
                status="staging",
                notes="enrich-candidate",
            )
        )
    return out


def enrich(paths: list[Path], *, out_name: str = "candidates.csv") -> Path:
    existing = {normalize_source(k) for k in build_merged_dict().keys()}
    pairs: list[tuple[str, str]] = []
    for p in paths:
        p = Path(p)
        if not p.is_file():
            continue
        if p.suffix.lower() == ".csv":
            pairs.extend(_load_pair_csv(p))
    entries = _candidate_entries(pairs, existing)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    out = STAGING_DIR / out_name
    # append if exists
    prior = load_glossary_csv(out, curated_only=False) if out.is_file() else []
    prior_keys = {normalize_source(e.source) for e in prior}
    merged_entries = list(prior)
    for e in entries:
        if normalize_source(e.source) not in prior_keys:
            merged_entries.append(e)
            prior_keys.add(normalize_source(e.source))
    write_glossary_csv(out, merged_entries)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="术语候选挖词 → staging")
    ap.add_argument("inputs", nargs="+", type=Path, help="glossary CSV 路径")
    ap.add_argument("--out-name", default="candidates.csv")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        existing = {normalize_source(k) for k in build_merged_dict().keys()}
        pairs: list[tuple[str, str]] = []
        for p in args.inputs:
            if Path(p).is_file():
                pairs.extend(_load_pair_csv(Path(p)))
        entries = _candidate_entries(pairs, existing)
        print(f"dry-run candidates={len(entries)}")
        for e in entries[:20]:
            print(f"  {e.source} => {e.target}")
        return 0
    out = enrich(args.inputs, out_name=args.out_name)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

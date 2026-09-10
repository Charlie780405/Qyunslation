#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-039d：将 staging 候选晋升到 org/clinical/project curated 表。"""
from __future__ import annotations

import argparse
from pathlib import Path

from qyunslation.glossary.governance import (
    GLOSSARIES_DIR,
    GlossaryEntry,
    load_glossary_csv,
    normalize_source,
    write_glossary_csv,
)

LAYER_FILES = {
    "org": GLOSSARIES_DIR / "org-proper-nouns.csv",
    "clinical": GLOSSARIES_DIR / "clinical-lifecycle.csv",
    "project": GLOSSARIES_DIR / "project-overlay.csv",
}


def promote(
    staging_path: Path,
    *,
    layer: str,
    sources: list[str] | None = None,
    domain: str = "",
    sponsor: str = "",
) -> int:
    if layer not in LAYER_FILES:
        raise SystemExit(f"layer must be one of {sorted(LAYER_FILES)}")
    staging = load_glossary_csv(staging_path, curated_only=False)
    if sources:
        want = {normalize_source(s) for s in sources}
        staging = [e for e in staging if normalize_source(e.source) in want]
    if not staging:
        print("nothing to promote")
        return 0
    dest = LAYER_FILES[layer]
    existing = load_glossary_csv(dest, default_layer=layer, curated_only=False)
    existing_keys = {normalize_source(e.source) for e in existing}
    added = 0
    for e in staging:
        key = normalize_source(e.source)
        if key in existing_keys:
            continue
        existing.append(
            GlossaryEntry(
                source=e.source,
                target=e.target,
                src_lng=e.src_lng,
                tgt_lng=e.tgt_lng,
                layer=layer,
                domain=domain or e.domain,
                sponsor=sponsor or e.sponsor,
                status="curated",
                notes=e.notes or "promoted",
            )
        )
        existing_keys.add(key)
        added += 1
    write_glossary_csv(dest, existing)
    # mark promoted as rejected in staging (keep audit)
    remaining: list[GlossaryEntry] = []
    promoted_keys = {normalize_source(e.source) for e in staging}
    for e in load_glossary_csv(staging_path, curated_only=False):
        if normalize_source(e.source) in promoted_keys:
            remaining.append(
                GlossaryEntry(
                    source=e.source,
                    target=e.target,
                    src_lng=e.src_lng,
                    tgt_lng=e.tgt_lng,
                    layer=e.layer,
                    domain=e.domain,
                    sponsor=e.sponsor,
                    status="rejected",
                    notes="promoted",
                )
            )
        else:
            remaining.append(e)
    write_glossary_csv(staging_path, remaining)
    print(f"promoted {added} → {dest}")
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description="staging → curated promote")
    ap.add_argument("staging", type=Path, help="staging CSV")
    ap.add_argument("--layer", required=True, choices=sorted(LAYER_FILES))
    ap.add_argument("--source", action="append", default=[], help="只晋升指定 source（可多次）")
    ap.add_argument("--domain", default="")
    ap.add_argument("--sponsor", default="")
    args = ap.parse_args()
    promote(
        args.staging,
        layer=args.layer,
        sources=args.source or None,
        domain=args.domain,
        sponsor=args.sponsor,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-039e：合并 curated(+可选 harvest) → merged.csv，并同步到 pdf2zh。"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from qyunslation.glossary.governance import (
    GLOSSARIES_DIR,
    GlossaryEntry,
    build_merged_dict,
    load_curated_entries,
    load_glossary_csv,
    merge_entries_list,
    write_glossary_csv,
)

DEFAULT_RUNTIME = Path("/home/dev/pdf2zh/glossaries/merged.csv")
REPO_MERGED = GLOSSARIES_DIR / "merged.csv"
HARVEST = GLOSSARIES_DIR / "auto-proper-nouns.csv"


def build_merged_entries(*, include_harvest: bool = True) -> list[GlossaryEntry]:
    entries = list(load_curated_entries())
    if include_harvest and HARVEST.is_file():
        entries.extend(
            load_glossary_csv(HARVEST, default_layer="harvest", curated_only=False, skip_junk=True)
        )
    return merge_entries_list(entries)


def sync_merged(
    *,
    runtime_path: Path = DEFAULT_RUNTIME,
    include_harvest: bool = True,
    also_copy_org: bool = True,
) -> Path:
    entries = build_merged_entries(include_harvest=include_harvest)
    write_glossary_csv(REPO_MERGED, entries)
    runtime_path = Path(runtime_path)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_MERGED, runtime_path)
    if also_copy_org:
        # keep legacy filenames in sync for any leftover config
        for name in (
            "org-proper-nouns.csv",
            "regulatory-form-fields.csv",
            "clinical-lifecycle.csv",
            "project-overlay.csv",
        ):
            src = GLOSSARIES_DIR / name
            if src.is_file():
                shutil.copy2(src, runtime_path.parent / name)
    return runtime_path


def main() -> int:
    ap = argparse.ArgumentParser(description="生成并同步 merged.csv")
    ap.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    ap.add_argument("--no-harvest", action="store_true")
    ap.add_argument("--print-count", action="store_true")
    args = ap.parse_args()
    path = sync_merged(
        runtime_path=args.runtime, include_harvest=not args.no_harvest
    )
    d = build_merged_dict(harvest_path=None if args.no_harvest else HARVEST)
    print(f"merged entries={len(d)} → {path}")
    if args.print_count:
        print(len(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# plan034a-materialize-gold — PLAN-034a1 gold root materializer
"""PLAN-034a1：物化本机金标（真件 symlink + 合成占位）并重写 catalog.json。

二进制只写 GOLD_ROOT，不入库。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.gold.plan034 import (  # noqa: E402
    CatalogCompletenessError,
    assert_catalog_complete,
    catalog_path,
    gold_root,
)
from qyunslation.gold.synthesize import sha256_file, write_placeholder_pdf  # noqa: E402

REPO = ROOT


@dataclass(frozen=True)
class Slot:
    id: str
    class_: str
    title: str
    relpath: str
    # ordered candidates for real files; empty → synthetic only
    real_candidates: tuple[Path, ...] = ()
    extra_tags: tuple[str, ...] = ()


def _slots() -> list[Slot]:
    hermes = Path("/home/dev/.hermes/attachments")
    fixtures = REPO / "tests" / "fixtures" / "structure" / "reference"
    pdf2zh = Path("/home/dev/pdf2zh/pdf2zh_files")
    qna = pdf2zh / "57114032-8727-41f9-b826-b5ff40fcf733" / "QX027N QnA-2026.08.19-临床.pdf"
    pind_dir = pdf2zh / "5fa54bcf-4843-4e97-8cd0-85c797fa9b5d"
    job_ljae = (
        pdf2zh / "ffc3aa5e-b7f3-4955-9470-b59334367fdf" / "ljae439.pdf"
    )
    return [
        # L — keep existing seed filenames for 033 / ljae439
        Slot(
            "L-033-elsevier-ad",
            "L",
            "PLAN-033 Elsevier AD 11-page literature sample",
            "plan033-elsevier-ad.pdf",
            (
                hermes / "1-s2.0-S2666636725013958-main.pdf",
            ),
            ("literature", "plan033", "seed"),
        ),
        Slot(
            "L-ljae439",
            "L",
            "ljae439 tralokinumab literature PDF",
            "ljae439.pdf",
            (job_ljae, fixtures / "ljae439.pdf"),
            ("literature", "table3", "seed"),
        ),
        Slot(
            "L-nature-comm-53384",
            "L",
            "Nature Communications 53384 literature fixture",
            "L-nature-comm-53384.pdf",
            (fixtures / "nature_comm_53384.pdf",),
            ("literature", "fixture"),
        ),
        Slot(
            "L-cai-2025-cont",
            "L",
            "CAI 2025 continued table literature fixture",
            "L-cai-2025-cont.pdf",
            (fixtures / "cai-2025-table1-continued.pdf",),
            ("literature", "fixture"),
        ),
        Slot(
            "L-nejm-392-12",
            "L",
            "NEJM 2025 vol 392 issue 12 fulltext attachment",
            "L-nejm-392-12.pdf",
            (hermes / "外刊全文_2025_0028-4793_392_12_77687295.pdf",),
            ("literature", "attachment"),
        ),
        Slot(
            "L-lancet-rm-13-1",
            "L",
            "Lancet Respir Med 2025 vol 13 issue 1 fulltext attachment",
            "L-lancet-rm-13-1.pdf",
            (hermes / "外刊全文_2025_2213-2600_13_1_77902936.pdf",),
            ("literature", "attachment"),
        ),
        *[
            Slot(
                f"L-{i:02d}",
                "L",
                f"Literature gold placeholder {i}",
                f"L-{i:02d}.pdf",
                (),
                ("synthetic-slot",),
            )
            for i in range(7, 11)
        ],
        # C
        Slot(
            "C-qx027n-qna",
            "C",
            "QX027N clinical QnA slide deck (not strict CSP)",
            "C-qx027n-qna.pdf",
            (qna,),
            ("clinical-qna",),
        ),
        Slot(
            "C-fda-pind",
            "C",
            "FDA responses on PIND scanned regulatory correspondence",
            "C-fda-pind.pdf",
            (pind_dir / "FDA responses on PIND.pdf",),
            ("pind",),
        ),
        Slot(
            "C-fda-pind-ocr",
            "C",
            "FDA responses on PIND HPD-OCR layer PDF",
            "C-fda-pind-ocr.pdf",
            (pind_dir / "FDA responses on PIND.hpd-ocr.pdf",),
            ("pind", "ocr"),
        ),
        *[
            Slot(
                f"C-{i:02d}",
                "C",
                f"Protocol / IB / CSR placeholder; Protocol Number: QY-034A1-C-{i:02d}",
                f"C-{i:02d}.pdf",
                (),
                ("synthetic-slot",),
            )
            for i in range(4, 11)
        ],
        # R — all synthetic
        *[
            Slot(
                f"R-{i:02d}",
                "R",
                f"CTD Module 2 Quality Overall Summary placeholder {i:02d}",
                f"R-{i:02d}.pdf",
                (),
                ("synthetic-slot", "ctd-m2"),
            )
            for i in range(1, 11)
        ],
    ]


def _link_or_copy(src: Path, dest: Path, *, dry_run: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return
    if dest.is_symlink() or dest.exists():
        dest.unlink()
    os.symlink(src.resolve(), dest)


def materialize_one(
    slot: Slot, root: Path, *, dry_run: bool
) -> tuple[dict, str]:
    """返回 (catalog_entry_dict, kind) kind=real|synthetic."""
    dest = root / slot.class_ / slot.relpath
    chosen: Path | None = None
    for cand in slot.real_candidates:
        if cand.is_file():
            chosen = cand
            break
        print(f"WARN skip missing: {cand}")

    if chosen is not None:
        print(f"REAL {slot.id} <- {chosen}")
        if not dry_run:
            _link_or_copy(chosen, dest, dry_run=False)
            digest = sha256_file(dest)
        else:
            digest = sha256_file(chosen)
        tags = ["real", *slot.extra_tags]
        kind = "real"
    else:
        print(f"SYNTH {slot.id} -> {dest}")
        if not dry_run:
            digest = write_placeholder_pdf(
                dest,
                gold_class=slot.class_,
                entry_id=slot.id,
                title=slot.title,
            )
        else:
            digest = "dry-run"
        tags = ["synthetic", *slot.extra_tags]
        kind = "synthetic"

    entry = {
        "id": slot.id,
        "class": slot.class_,
        "title": slot.title,
        "format": "pdf",
        "lang_pair": "en→zh",
        "sha256": digest,
        "relpath": slot.relpath,
        "tags": list(tags),
        "status": "ready",
    }
    return entry, kind


def main() -> int:
    ap = argparse.ArgumentParser(description="PLAN-034a1 materialize gold root + catalog")
    ap.add_argument("--gold-root", type=Path, default=None)
    ap.add_argument("--catalog", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-assert", action="store_true")
    args = ap.parse_args()

    root = gold_root(args.gold_root)
    cat_path = catalog_path(args.catalog)
    slots = _slots()
    assert len(slots) == 30, len(slots)

    entries: list[dict] = []
    counts = {"real": 0, "synthetic": 0, "L": 0, "C": 0, "R": 0}
    for slot in slots:
        entry, kind = materialize_one(slot, root, dry_run=args.dry_run)
        entries.append(entry)
        counts[kind] += 1
        counts[slot.class_] += 1

    catalog = {
        "schema_version": "1.0.0",
        "plan": "PLAN-034a1",
        "description": (
            "Pharma gold catalog; binaries under QYUNSLATION_PLAN034_GOLD_ROOT. "
            "tags: real|synthetic"
        ),
        "entries": entries,
    }

    if args.dry_run:
        print(json.dumps({"counts": counts, "n": len(entries)}, ensure_ascii=False, indent=2))
        return 0

    cat_path.parent.mkdir(parents=True, exist_ok=True)
    cat_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {cat_path} entries={len(entries)} counts={counts}")

    if not args.skip_assert:
        try:
            summary = assert_catalog_complete(root=root)
            print("assert_catalog_complete PASS", summary)
        except CatalogCompletenessError as exc:
            print("assert_catalog_complete FAIL", exc)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

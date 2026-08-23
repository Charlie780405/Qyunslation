# SPDX-License-Identifier: MPL-2.0
"""PLAN-005：从静态 CSV 加载术语表。"""
from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def load_static_glossary(path: str | Path | None = None) -> dict[str, str]:
    path = Path(
        path
        or os.environ.get(
            "QYUNSLATION_GLOSSARY_CSV",
            "/home/dev/pdf2zh/glossaries/qx027n.csv",
        )
    )
    if not path.is_file():
        logger.warning("static glossary missing: %s", path)
        return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src = (row.get("source") or "").strip()
            tgt = (row.get("target") or "").strip()
            if src and tgt:
                out[src] = tgt
    logger.info("loaded static glossary %s entries from %s", len(out), path)
    return out

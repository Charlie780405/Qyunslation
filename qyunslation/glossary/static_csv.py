# SPDX-License-Identifier: MPL-2.0
"""PLAN-005 / PLAN-039：从静态 CSV 加载术语表（默认 merged）。"""
from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_MERGED = "/home/dev/pdf2zh/glossaries/merged.csv"
_FALLBACK_QX = "/home/dev/pdf2zh/glossaries/qx027n.csv"


def load_static_glossary(path: str | Path | None = None) -> dict[str, str]:
    if path is None:
        env = os.environ.get("QYUNSLATION_GLOSSARY_CSV")
        if env:
            path = Path(env)
        else:
            merged = Path(_DEFAULT_MERGED)
            path = merged if merged.is_file() else Path(_FALLBACK_QX)
    else:
        path = Path(path)
    if not path.is_file():
        # last resort: in-repo merge via governance
        try:
            from qyunslation.glossary.governance import build_merged_dict

            out = build_merged_dict()
            logger.info("loaded static glossary %s entries via governance merge", len(out))
            return out
        except Exception:
            logger.warning("static glossary missing: %s", path)
            return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src = (row.get("source") or row.get("src") or "").strip()
            tgt = (row.get("target") or row.get("dst") or "").strip()
            if src and tgt:
                out[src] = tgt
    logger.info("loaded static glossary %s entries from %s", len(out), path)
    return out

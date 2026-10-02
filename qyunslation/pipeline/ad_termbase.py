"""PLAN-076d: AD concept seed and direction-aware runtime term policy."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Iterable

_TERMS_PATH = Path(__file__).resolve().parents[2] / "glossaries" / "domain-ad.csv"


def _truthy(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "是"}


def load_ad_terms(path: str | Path | None = None) -> list[dict]:
    source = Path(path) if path else _TERMS_PATH
    with source.open("r", encoding="utf-8", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            item = {key: (value or "").strip() for key, value in row.items()}
            item["do_not_translate"] = _truthy(item.get("do_not_translate", ""))
            item["risk"] = item.get("risk") or ("high" if item.get("term_type") in {"drug", "target"} else "normal")
            rows.append(item)
        return rows


def _direction_rows(direction: str, rows: Iterable[dict]) -> list[dict]:
    if direction == "en-zh":
        return [row for row in rows if row.get("src_lang") == "en" and row.get("tgt_lang") == "zh"]
    if direction == "zh-en":
        return [
            {
                **row,
                "source": row.get("target", ""),
                "target": row.get("source", ""),
                "src_lang": "zh",
                "tgt_lang": "en",
            }
            for row in rows
            if row.get("src_lang") == "en" and row.get("tgt_lang") == "zh"
        ]
    raise ValueError("unsupported AD direction")


def _contains(text: str, term: str) -> bool:
    if not term:
        return False
    if any(ord(char) > 127 for char in term):
        return term in text
    import re

    return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.I))


def build_ad_term_policy(text: str, direction: str) -> dict:
    rows = sorted(_direction_rows(direction, load_ad_terms()), key=lambda row: len(row.get("source", "")), reverse=True)
    terms: dict[str, str] = {}
    metadata: list[dict] = []
    for row in rows:
        source = row.get("source", "")
        if source and source not in terms and _contains(text or "", source):
            terms[source] = row.get("target", "")
            metadata.append(
                {
                    "source_term": source,
                    "target_term": row.get("target", ""),
                    "term_type": row.get("term_type", "general"),
                    "risk": row.get("risk", "normal"),
                    "do_not_translate": bool(row.get("do_not_translate")),
                    "forbidden_targets": [item for item in row.get("forbidden_targets", "").split("|") if item],
                }
            )
    digest_payload = "|".join(f"{key}={value}" for key, value in sorted(terms.items()))
    version = "076-ad-" + hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()[:16]
    return {
        "schema": "076-ad-termbase-v1",
        "direction": direction,
        "termbase_version": version,
        "terms": terms,
        "metadata": metadata,
    }

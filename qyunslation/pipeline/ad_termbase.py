"""PLAN-076d/076i: AD concept SSOT and direction-aware runtime term policy."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Iterable

_CONCEPTS_PATH = Path(__file__).resolve().parents[2] / "glossaries" / "domain-ad-concepts.csv"
_LEGACY_PATH = Path(__file__).resolve().parents[2] / "glossaries" / "domain-ad.csv"


def _truthy(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "是"}


def load_ad_concepts(path: str | Path | None = None) -> list[dict]:
    source = Path(path) if path else _CONCEPTS_PATH
    if not source.is_file():
        return _load_legacy_rows(_LEGACY_PATH)
    with source.open("r", encoding="utf-8", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            item = {key: (value or "").strip() for key, value in row.items() if key}
            item["do_not_translate"] = _truthy(item.get("do_not_translate", ""))
            item["risk"] = item.get("risk") or ("high" if item.get("term_type") in {"drug", "target"} else "normal")
            item["en_aliases"] = _split_aliases(item.get("en_aliases", ""))
            item["zh_aliases"] = _split_aliases(item.get("zh_aliases", ""))
            rows.append(item)
        return rows


def _split_aliases(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def _load_legacy_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "concept_id": f"legacy-{len(rows)}",
                    "en": row.get("source", ""),
                    "zh": row.get("target", ""),
                    "term_type": row.get("term_type", "general"),
                    "risk": row.get("risk", "normal"),
                    "do_not_translate": _truthy(row.get("do_not_translate", "")),
                    "forbidden_targets": row.get("forbidden_targets", ""),
                    "status": "legacy",
                    "en_aliases": [],
                    "zh_aliases": [],
                }
            )
        return rows


def _direction_rows(direction: str, rows: Iterable[dict]) -> list[dict]:
    curated = [row for row in rows if row.get("status", "curated") != "deprecated"]
    if direction == "en-zh":
        return [
            {
                **row,
                "source": row.get("en", ""),
                "target": row.get("zh", ""),
                "target_aliases": _split_aliases(row.get("zh_aliases", [])),
                "src_lang": "en",
                "tgt_lang": "zh",
            }
            for row in curated
            if row.get("en") and row.get("zh")
        ]
    if direction == "zh-en":
        return [
            {
                **row,
                "source": row.get("zh", ""),
                "target": row.get("en", ""),
                "target_aliases": _split_aliases(row.get("en_aliases", [])),
                "src_lang": "zh",
                "tgt_lang": "en",
            }
            for row in curated
            if row.get("en") and row.get("zh")
        ]
    raise ValueError("unsupported AD direction")


def _contains(text: str, term: str) -> bool:
    if not term:
        return False
    if any(ord(char) > 127 for char in term):
        return term in text
    import re

    # "20 mg" must match "20mg" and vice versa; "flare" must match "flares".
    escaped = re.escape(term).replace(r"\ ", r"\s*")
    escaped = re.sub(r"(?<=\d)(?=[A-Za-zμµ%])", r"\\s*", escaped)
    pattern = r"(?<![A-Za-z0-9])" + escaped + r"(?:s|es)?(?![A-Za-z0-9])"
    return bool(re.search(pattern, text, re.I))


def load_ad_terms(path: str | Path | None = None) -> list[dict]:
    """Backward-compatible en→zh view of the concept SSOT."""
    return [
        {
            **row,
            "source": row.get("en", ""),
            "target": row.get("zh", ""),
            "src_lang": "en",
            "tgt_lang": "zh",
        }
        for row in load_ad_concepts(path)
    ]


def build_ad_term_policy(text: str, direction: str) -> dict:
    rows = sorted(_direction_rows(direction, load_ad_concepts()), key=lambda row: len(row.get("source", "")), reverse=True)
    terms: dict[str, str] = {}
    aliases: dict[str, tuple[str, ...]] = {}
    metadata: list[dict] = []
    for row in rows:
        source = row.get("source", "")
        if source and source not in terms and _contains(text or "", source):
            terms[source] = row.get("target", "")
            accepted = tuple(item for item in row.get("target_aliases") or () if item and item != terms[source])
            if accepted:
                aliases[source] = accepted
            metadata.append(
                {
                    "concept_id": row.get("concept_id"),
                    "source_term": source,
                    "target_term": row.get("target", ""),
                    "target_aliases": list(accepted),
                    "term_type": row.get("term_type", "general"),
                    "risk": row.get("risk", "normal"),
                    "do_not_translate": bool(row.get("do_not_translate")),
                    "forbidden_targets": [item for item in str(row.get("forbidden_targets", "")).split("|") if item],
                    "status": row.get("status", "curated"),
                }
            )
    digest_payload = "|".join(f"{key}={value}" for key, value in sorted(terms.items()))
    version = "076-ad-" + hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()[:16]
    return {
        "schema": "076-ad-termbase-v1",
        "direction": direction,
        "termbase_version": version,
        "terms": terms,
        "aliases": aliases,
        "metadata": metadata,
    }

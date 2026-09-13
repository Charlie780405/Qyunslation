# SPDX-License-Identifier: MPL-2.0
"""PLAN-039：术语治理 — schema、加载、按优先级合并。"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Iterable

FIELDNAMES = (
    "source",
    "target",
    "src_lng",
    "tgt_lng",
    "layer",
    "domain",
    "sponsor",
    "status",
    "notes",
)

LAYER_PRIORITY = {
    "org": 100,
    "form": 90,  # PLAN-042b：登记表固定字段 / 短值格，介于 org 与 clinical
    "clinical": 80,
    "project": 60,
    "session": 40,
    "harvest": 20,
}

VALID_LAYERS = frozenset(LAYER_PRIORITY)
VALID_STATUS = frozenset({"curated", "staging", "rejected"})
VALID_DOMAINS = frozenset(
    {
        "org",
        "discovery",
        "cmc",
        "nonclinical",
        "clinpharm",
        "clinical",
        "safety",
        "regulatory",
        "stats",
        "ip",
        "heor",
        "",
    }
)

# 禁止进 curated 的垃圾模式
_JUNK_SOURCE = re.compile(
    r"(?ix)^("
    r"page\s*\d+"
    r"|question\s*\d+"
    r"|fda\s+response\s+to\s+question"
    r"|september\s+\d{1,2},\s*\d{4}"
    r"|april\s+\d{1,2},\s*\d{4}"
    r"|august\s+\d{1,2},\s*\d{4}"
    r"|\d{1,2}:\d{2}\s*(am|pm)"
    r"|20\d{2}年\d{1,2}月"
    r")$"
)
_JUNK_LONG_SENTENCE = re.compile(r"[.。].*[.。]| is being developed ")

ROOT = Path(__file__).resolve().parents[2]
GLOSSARIES_DIR = ROOT / "glossaries"


@dataclass(frozen=True)
class GlossaryEntry:
    source: str
    target: str
    src_lng: str = ""
    tgt_lng: str = ""
    layer: str = "clinical"
    domain: str = ""
    sponsor: str = ""
    status: str = "curated"
    notes: str = ""

    def merge_key(self) -> tuple[str, str]:
        return (normalize_lang(self.src_lng), normalize_source(self.source))


def normalize_source(source: str) -> str:
    return " ".join((source or "").strip().split()).casefold()


def normalize_lang(lang: str) -> str:
    raw = (lang or "").strip().casefold()
    if raw in {"", "en", "eng", "english"}:
        return "en" if raw else ""
    if raw in {"zh", "zh-cn", "zh_cn", "cn", "chinese", "中文", "简体中文"}:
        return "zh"
    return raw


def infer_src_lng(source: str, explicit: str = "") -> str:
    if explicit and explicit.strip():
        return normalize_lang(explicit)
    # CJK → zh
    if re.search(r"[\u4e00-\u9fff]", source or ""):
        return "zh"
    return "en"


def is_junk_source(source: str) -> bool:
    s = (source or "").strip()
    if not s:
        return True
    if _JUNK_SOURCE.match(s):
        return True
    if len(s) > 120 and _JUNK_LONG_SENTENCE.search(s):
        return True
    return False


def entry_from_row(row: dict[str, str], *, default_layer: str = "clinical") -> GlossaryEntry | None:
    source = (row.get("source") or row.get("src") or "").strip()
    target = (row.get("target") or row.get("dst") or "").strip()
    if not source or not target:
        return None
    src_lng = infer_src_lng(source, row.get("src_lng") or "")
    tgt_lng = normalize_lang(row.get("tgt_lng") or "")
    layer = (row.get("layer") or default_layer).strip().casefold() or default_layer
    if layer not in VALID_LAYERS:
        layer = default_layer
    status = (row.get("status") or "curated").strip().casefold() or "curated"
    if status not in VALID_STATUS:
        status = "curated"
    domain = (row.get("domain") or "").strip().casefold()
    if domain not in VALID_DOMAINS:
        domain = ""
    return GlossaryEntry(
        source=source,
        target=target,
        src_lng=src_lng,
        tgt_lng=tgt_lng,
        layer=layer,
        domain=domain,
        sponsor=(row.get("sponsor") or "").strip(),
        status=status,
        notes=(row.get("notes") or "").strip(),
    )


def load_glossary_csv(
    path: Path | str,
    *,
    default_layer: str = "clinical",
    curated_only: bool = True,
    skip_junk: bool = False,
) -> list[GlossaryEntry]:
    path = Path(path)
    if not path.is_file():
        return []
    out: list[GlossaryEntry] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry = entry_from_row(row, default_layer=default_layer)
            if entry is None:
                continue
            if curated_only and entry.status != "curated":
                continue
            if skip_junk and is_junk_source(entry.source):
                continue
            out.append(entry)
    return out


def merge_by_priority(entries: Iterable[GlossaryEntry]) -> dict[str, str]:
    """按 layer 优先级合并为 {source: target}。

    同 merge_key 时高优先级胜；同优先级保留先写入（调用方应先放高优层）。
    输出字典键保留**原样 source**（首个胜出条目的展示形式）。
    """
    winners: dict[tuple[str, str], GlossaryEntry] = {}
    for entry in entries:
        if entry.status == "rejected":
            continue
        key = entry.merge_key()
        prev = winners.get(key)
        if prev is None:
            winners[key] = entry
            continue
        if LAYER_PRIORITY.get(entry.layer, 0) > LAYER_PRIORITY.get(prev.layer, 0):
            winners[key] = entry
    # 同一 normalized source 若多语言键冲突，仍按各自 source 原文输出
    result: dict[str, str] = {}
    for entry in winners.values():
        result[entry.source] = entry.target
    return result


def merge_entries_list(entries: Iterable[GlossaryEntry]) -> list[GlossaryEntry]:
    winners: dict[tuple[str, str], GlossaryEntry] = {}
    for entry in entries:
        if entry.status == "rejected":
            continue
        key = entry.merge_key()
        prev = winners.get(key)
        if prev is None or LAYER_PRIORITY.get(entry.layer, 0) > LAYER_PRIORITY.get(
            prev.layer, 0
        ):
            winners[key] = entry
    return sorted(winners.values(), key=lambda e: (e.layer, e.source.casefold()))


def write_glossary_csv(path: Path | str, entries: Iterable[GlossaryEntry]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(entries)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for e in rows:
            w.writerow({f.name: getattr(e, f.name) for f in fields(e)})
    return len(rows)


def default_curated_paths(root: Path | None = None) -> list[Path]:
    base = root or GLOSSARIES_DIR
    return [
        base / "org-proper-nouns.csv",
        base / "regulatory-form-fields.csv",
        base / "clinical-lifecycle.csv",
        base / "project-overlay.csv",
    ]


def load_curated_entries(root: Path | None = None) -> list[GlossaryEntry]:
    """按优先级顺序加载 curated 表（org → form → clinical → project）。"""
    layer_defaults = ("org", "form", "clinical", "project")
    entries: list[GlossaryEntry] = []
    for path, layer in zip(default_curated_paths(root), layer_defaults):
        entries.extend(
            load_glossary_csv(path, default_layer=layer, curated_only=True, skip_junk=True)
        )
    return entries


def build_merged_dict(
    root: Path | None = None,
    *,
    harvest_path: Path | None = None,
    session_entries: Iterable[GlossaryEntry] | None = None,
) -> dict[str, str]:
    # PLAN-034d：有 Concept 库且含 curated 时优先用扁平视图，再叠 session/harvest 文件
    db_entries: list[GlossaryEntry] | None = None
    try:
        from qyunslation.glossary.concept_flatten import try_db_curated_entries

        db_entries = try_db_curated_entries()
    except Exception:
        db_entries = None

    if db_entries is not None:
        entries: list[GlossaryEntry] = list(db_entries)
    else:
        entries = list(load_curated_entries(root))
    if session_entries:
        entries.extend(session_entries)
    if harvest_path and Path(harvest_path).is_file():
        entries.extend(
            load_glossary_csv(
                harvest_path, default_layer="harvest", curated_only=False, skip_junk=True
            )
        )
    return merge_by_priority(entries)

# SPDX-License-Identifier: MPL-2.0
"""PLAN-034a：医药金标清单加载、哈希校验与完备性断言。"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

GoldClass = Literal["L", "C", "R"]
GoldStatus = Literal["ready", "pending"]

DEFAULT_GOLD_ROOT = Path("/home/dev/qyunslation-gold/plan034")
GOLD_ROOT_ENV = "QYUNSLATION_PLAN034_GOLD_ROOT"
REPO_CATALOG = Path(__file__).resolve().parents[2] / "docs" / "gold" / "plan034" / "catalog.json"
REPO_THRESHOLDS = Path(__file__).resolve().parents[2] / "docs" / "gold" / "plan034" / "thresholds.toml"


@dataclass(frozen=True)
class GoldEntry:
    id: str
    class_: GoldClass
    title: str
    format: str
    lang_pair: str
    sha256: str
    relpath: str
    tags: tuple[str, ...] = ()
    status: GoldStatus = "pending"
    artifact_mono: str = ""

    @property
    def gold_class(self) -> GoldClass:
        return self.class_


@dataclass
class CatalogCompletenessError(Exception):
    """三类 ready 不足或文件/哈希不匹配。"""

    reasons: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "catalog incomplete"


def gold_root(override: Path | str | None = None) -> Path:
    if override is not None:
        return Path(override)
    env = os.environ.get(GOLD_ROOT_ENV, "").strip()
    if env:
        return Path(env)
    return DEFAULT_GOLD_ROOT


def catalog_path(override: Path | str | None = None) -> Path:
    return Path(override) if override is not None else REPO_CATALOG


def thresholds_path(override: Path | str | None = None) -> Path:
    return Path(override) if override is not None else REPO_THRESHOLDS


def _sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def load_catalog(path: Path | str | None = None) -> list[GoldEntry]:
    p = catalog_path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    entries_raw = raw.get("entries") if isinstance(raw, dict) else raw
    if not isinstance(entries_raw, list):
        raise ValueError(f"catalog entries must be a list: {p}")
    out: list[GoldEntry] = []
    for row in entries_raw:
        if not isinstance(row, dict):
            raise ValueError(f"catalog entry must be object: {row!r}")
        cls = str(row.get("class") or "").strip().upper()
        if cls not in {"L", "C", "R"}:
            raise ValueError(f"invalid class {cls!r} in {row.get('id')}")
        status = str(row.get("status") or "pending").strip().lower()
        if status not in {"ready", "pending"}:
            raise ValueError(f"invalid status {status!r} in {row.get('id')}")
        tags = row.get("tags") or []
        if not isinstance(tags, list):
            raise ValueError(f"tags must be list in {row.get('id')}")
        out.append(
            GoldEntry(
                id=str(row.get("id") or "").strip(),
                class_=cls,  # type: ignore[arg-type]
                title=str(row.get("title") or "").strip(),
                format=str(row.get("format") or "").strip(),
                lang_pair=str(row.get("lang_pair") or "en→zh").strip(),
                sha256=str(row.get("sha256") or "").strip().lower(),
                relpath=str(row.get("relpath") or "").strip(),
                tags=tuple(str(t) for t in tags),
                status=status,  # type: ignore[arg-type]
                artifact_mono=str(row.get("artifact_mono") or "").strip(),
            )
        )
        if not out[-1].id:
            raise ValueError("catalog entry missing id")
    return out


def resolve_entry(entry: GoldEntry, root: Path | str | None = None) -> Path | None:
    """返回本机文件路径；不存在则 None。不在此校验哈希。"""
    base = gold_root(root)
    if not entry.relpath:
        return None
    path = base / entry.class_ / entry.relpath
    return path if path.is_file() else None


def verify_entry_hash(entry: GoldEntry, path: Path) -> bool:
    if not entry.sha256 or len(entry.sha256) != 64:
        return False
    return _sha256_file(path) == entry.sha256


def ready_entries(entries: Iterable[GoldEntry]) -> list[GoldEntry]:
    return [e for e in entries if e.status == "ready"]


def assert_catalog_complete(
    entries: list[GoldEntry] | None = None,
    *,
    root: Path | str | None = None,
    min_per_class: int = 10,
) -> dict[str, Any]:
    """三类各 ≥min_per_class 且 ready 文件存在、哈希匹配。失败抛 CatalogCompletenessError。"""
    items = list(entries) if entries is not None else load_catalog()
    base = gold_root(root)
    reasons: list[str] = []
    by_class: dict[str, list[GoldEntry]] = {"L": [], "C": [], "R": []}
    for e in ready_entries(items):
        by_class[e.class_].append(e)

    for cls in ("L", "C", "R"):
        if len(by_class[cls]) < min_per_class:
            reasons.append(
                f"class {cls}: ready={len(by_class[cls])} < {min_per_class}"
            )

    ok_files = 0
    for e in ready_entries(items):
        path = resolve_entry(e, base)
        if path is None:
            reasons.append(f"{e.id}: missing file under {base / e.class_ / e.relpath}")
            continue
        if not verify_entry_hash(e, path):
            reasons.append(f"{e.id}: sha256 mismatch for {path}")
            continue
        ok_files += 1

    if reasons:
        raise CatalogCompletenessError(reasons=reasons)
    return {
        "gold_root": str(base),
        "ready_total": len(ready_entries(items)),
        "ok_files": ok_files,
        "per_class": {k: len(v) for k, v in by_class.items()},
    }


def load_thresholds(path: Path | str | None = None) -> dict[str, Any]:
    import tomllib

    p = thresholds_path(path)
    with p.open("rb") as fh:
        data = tomllib.load(fh)
    required = (
        "version",
        "critical_max",
        "hard_term_hit_min",
        "forbidden_translation_max",
        "digit_unit_doi_ref_pass",
    )
    for key in required:
        if key not in data:
            raise ValueError(f"thresholds missing {key}: {p}")
    return data


def evaluate_baseline_report(report: dict[str, Any], thresholds: dict[str, Any] | None = None) -> str:
    """返回 'pass' 或 'fail'。report 键对齐 thresholds。"""
    th = thresholds if thresholds is not None else load_thresholds()
    critical = int(report.get("critical_count", 0))
    hard_hit = float(report.get("hard_term_hit_rate", 0.0))
    forbidden = int(report.get("forbidden_translation_count", 0))
    digit_pass = float(report.get("digit_unit_doi_ref_pass_rate", 0.0))
    if critical > int(th["critical_max"]):
        return "fail"
    if hard_hit < float(th["hard_term_hit_min"]):
        return "fail"
    if forbidden > int(th["forbidden_translation_max"]):
        return "fail"
    if digit_pass < float(th["digit_unit_doi_ref_pass"]):
        return "fail"
    return "pass"

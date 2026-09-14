# SPDX-License-Identifier: MPL-2.0
"""PLAN-052：synthetic→real promote（symlink + catalog tags/sha）。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from qyunslation.gold.plan034 import (
    CatalogCompletenessError,
    assert_catalog_complete,
    catalog_path,
    gold_root,
    load_catalog,
)
from qyunslation.gold.synthesize import sha256_file

REAL_SOURCES_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "gold" / "plan034" / "real-sources.json"
)

# class → 允许的 kind
ALLOWED_KIND: dict[str, frozenset[str]] = {
    "L": frozenset({"literature", "fixture", "attachment", "seed"}),
    "C": frozenset({"protocol", "clinical", "clinical-qna", "pind", "ocr", "cdp"}),
    "R": frozenset({"ctd-m2"}),
}


class Plan052PromoteError(ValueError):
    """类不诚实或文件缺失 → exit 2。"""


def load_real_sources(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path is not None else REAL_SOURCES_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise Plan052PromoteError(f"invalid real-sources.json: {p}")
    return raw


def source_row_for(entry_id: str, sources: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = sources if sources is not None else load_real_sources()
    for row in data.get("entries") or []:
        if isinstance(row, dict) and row.get("entry_id") == entry_id:
            return row
    return None


def inbox_dir(gold_class: str, *, root: Path | str | None = None) -> Path:
    return gold_root(root) / "inbox" / gold_class.upper()


def resolve_source_file(
    *,
    entry_id: str,
    from_path: Path | str | None = None,
    from_inbox: bool = False,
    sources: dict[str, Any] | None = None,
    root: Path | str | None = None,
) -> tuple[Path, str, list[str]]:
    """返回 (src_pdf, kind, extra_tags)。"""
    row = source_row_for(entry_id, sources)
    kind = ""
    extra: list[str] = []
    if row:
        kind = str(row.get("kind") or "").strip()
        extra = [str(t) for t in (row.get("extra_tags") or [])]
        cls = str(row.get("class") or "").strip().upper()
    else:
        cls = entry_id.split("-", 1)[0].upper() if "-" in entry_id else ""

    if from_path is not None:
        src = Path(from_path)
    elif from_inbox:
        if not row:
            raise Plan052PromoteError(f"{entry_id}: not in real-sources.json; pass --from")
        name = str(row.get("inbox_name") or "").strip()
        if not name:
            raise Plan052PromoteError(f"{entry_id}: inbox_name empty")
        src = inbox_dir(cls or str(row.get("class") or "X"), root=root) / name
        # 本机 hint 回退
        hint = str(row.get("host_hint") or "").strip()
        if not src.is_file() and hint and Path(hint).is_file():
            src = Path(hint)
    else:
        raise Plan052PromoteError("need --from or --from-inbox")

    if not src.is_file():
        raise Plan052PromoteError(f"source file missing: {src}")
    if not kind:
        raise Plan052PromoteError(f"{entry_id}: kind required (registry or --kind)")
    return src, kind, extra


def ensure_pdf_source(src: Path, *, work_dir: Path) -> Path:
    """PDF 原样返回；DOCX/DOC 经 LibreOffice 转 PDF（产物不入库）。"""
    suf = src.suffix.lower()
    if suf == ".pdf":
        return src
    if suf not in {".docx", ".doc"}:
        raise Plan052PromoteError(f"unsupported source type {suf}: {src}")
    work_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    import subprocess

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise Plan052PromoteError("LibreOffice (soffice) required to convert DOCX→PDF")
    # 拷到工作区避免中文路径/只读源问题
    local = work_dir / src.name
    if local.resolve() != src.resolve():
        shutil.copy2(src, local)
    proc = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work_dir),
            str(local),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    out_pdf = work_dir / (local.stem + ".pdf")
    if proc.returncode != 0 or not out_pdf.is_file():
        raise Plan052PromoteError(
            f"DOCX→PDF failed (exit {proc.returncode}): {proc.stderr[-400:]}"
        )
    return out_pdf


def assert_kind_allowed(entry_class: str, kind: str) -> None:
    cls = entry_class.upper()
    allowed = ALLOWED_KIND.get(cls)
    if allowed is None:
        raise Plan052PromoteError(f"unknown class {cls}")
    if kind not in allowed:
        raise Plan052PromoteError(
            f"kind {kind!r} not allowed for class {cls}; allowed={sorted(allowed)}"
        )


def _link_or_replace(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.exists():
        dest.unlink()
    os.symlink(src.resolve(), dest)


def load_catalog_raw(path: Path | str | None = None) -> dict[str, Any]:
    p = catalog_path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise Plan052PromoteError(f"invalid catalog: {p}")
    return raw


def write_catalog_raw(data: dict[str, Any], path: Path | str | None = None) -> Path:
    p = catalog_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def promote_entry(
    entry_id: str,
    *,
    src: Path,
    kind: str,
    extra_tags: list[str] | None = None,
    gold_root_path: Path | str | None = None,
    catalog: Path | str | None = None,
    dry_run: bool = False,
    skip_assert: bool = False,
) -> dict[str, Any]:
    """Promote one catalog entry to real."""
    raw = load_catalog_raw(catalog)
    entries: list[dict[str, Any]] = list(raw["entries"])
    idx = next((i for i, e in enumerate(entries) if e.get("id") == entry_id), None)
    if idx is None:
        raise Plan052PromoteError(f"entry not in catalog: {entry_id}")
    row = dict(entries[idx])
    cls = str(row.get("class") or "").upper()
    assert_kind_allowed(cls, kind)

    relpath = str(row.get("relpath") or "").strip()
    if not relpath:
        raise Plan052PromoteError(f"{entry_id}: missing relpath")
    base = gold_root(gold_root_path)
    dest = base / cls / relpath

    work = base / "inbox" / "_convert" / entry_id
    pdf_src = ensure_pdf_source(src, work_dir=work)

    digest = sha256_file(pdf_src)
    tags = ["real", kind, *(extra_tags or [])]
    # 去重保序
    seen: set[str] = set()
    clean_tags: list[str] = []
    for t in tags:
        if t and t not in seen and t not in {"synthetic", "synthetic-slot"}:
            seen.add(t)
            clean_tags.append(t)

    # 登记表标题优先
    reg = source_row_for(entry_id)
    if reg and reg.get("title"):
        title = str(reg["title"])
    elif kind == "protocol" and "Protocol" not in str(row.get("title") or ""):
        title = f"{row.get('title') or entry_id} (Protocol)"
    else:
        title = str(row.get("title") or entry_id)

    if dry_run:
        return {
            "entry_id": entry_id,
            "dry_run": True,
            "src": str(src),
            "pdf_src": str(pdf_src),
            "dest": str(dest),
            "sha256": digest,
            "tags": clean_tags,
            "class": cls,
            "kind": kind,
            "title": title,
        }

    # PDF：可 symlink；转换产物：复制进 GOLD_ROOT（仍不入库 git）
    if pdf_src.suffix.lower() == ".pdf" and src.suffix.lower() == ".pdf":
        _link_or_replace(pdf_src, dest)
    else:
        import shutil

        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        shutil.copy2(pdf_src, dest)

    digest2 = sha256_file(dest)
    if digest2 != digest:
        raise Plan052PromoteError(f"{entry_id}: hash mismatch after place")

    row["sha256"] = digest2
    row["tags"] = clean_tags
    row["status"] = "ready"
    row["title"] = title
    row["format"] = "pdf"
    entries[idx] = row
    raw["entries"] = entries
    write_catalog_raw(raw, catalog)

    if not skip_assert:
        try:
            assert_catalog_complete(root=base)
        except CatalogCompletenessError as exc:
            raise Plan052PromoteError(f"catalog incomplete after promote: {exc}") from exc

    return {
        "entry_id": entry_id,
        "src": str(src.resolve()),
        "pdf_src": str(pdf_src.resolve()),
        "dest": str(dest),
        "sha256": digest2,
        "tags": clean_tags,
        "class": cls,
        "kind": kind,
        "title": title,
    }


def real_counts(catalog_file: Path | str | None = None) -> dict[str, int]:
    counts = {"L": 0, "C": 0, "R": 0, "total": 0}
    for e in load_catalog(catalog_file):
        if e.status != "ready" or "real" not in e.tags:
            continue
        if e.class_ in counts:
            counts[e.class_] += 1
            counts["total"] += 1
    return counts


def product_ready(counts: dict[str, int] | None = None) -> bool:
    c = counts if counts is not None else real_counts()
    return c.get("L", 0) >= 1 and c.get("C", 0) >= 1 and c.get("R", 0) >= 1

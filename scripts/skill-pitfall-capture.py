#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-047g：从作业日志/imgtr/verify 沉淀踩坑签名。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIG_PATH = ROOT / ".cursor/skills/skill-registry/error-signatures.toml"
INBOX = ROOT / ".cursor/skills/skill-registry/pitfalls-inbox.md"
REGISTRY = ROOT / ".cursor/skills/skill-registry/registry.md"

SKILL_DIRS = {
    "SK-Q001": "scanned-doc-layout-fidelity",
    "SK-Q002": "image-overlay-translation",
    "SK-Q003": "pdf-regulatory-form-fidelity",
    "SK-Q004": "translate-stack-process-boundary",
    "SK-Q005": "babeldoc-patch-safety",
    "SK-Q006": "literature-paragraph-layout",
    "SK-Q007": "translation-content-integrity",
    "SK-Q008": "translation-pitfall-capture",
    "SK-Q009": "table-translation-fidelity",
}


def _load_signatures() -> list[dict]:
    if not SIG_PATH.is_file():
        return []
    # 极简 TOML 解析（本文件结构固定）
    text = SIG_PATH.read_text(encoding="utf-8")
    entries: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        s = line.strip()
        if s == "[[signature]]":
            if cur:
                entries.append(cur)
            cur = {}
            continue
        if cur is None or not s or s.startswith("#"):
            continue
        if "=" in s:
            k, v = s.split("=", 1)
            cur[k.strip()] = v.strip().strip('"')
    if cur:
        entries.append(cur)
    return entries


def _scan(text: str, signatures: list[dict]) -> tuple[dict[str, int], list[str]]:
    hits: dict[str, int] = {}
    unmatched: list[str] = []
    lines = [ln for ln in text.splitlines() if re.search(r"ERROR|WARNING", ln, re.I)]
    for ln in lines:
        matched = False
        for sig in signatures:
            pat = sig.get("pattern") or ""
            try:
                if re.search(pat, ln):
                    hits[sig["id"]] = hits.get(sig["id"], 0) + 1
                    matched = True
                    break
            except re.error:
                if pat in ln:
                    hits[sig["id"]] = hits.get(sig["id"], 0) + 1
                    matched = True
                    break
        if not matched:
            # 归一：去时间戳与路径数字
            norm = re.sub(r"\d+", "#", ln)
            unmatched.append(norm[:240])
    # 去重
    seen = set()
    uniq = []
    for u in unmatched:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return hits, uniq


def _suggest_skill(line: str) -> str:
    low = line.lower()
    if "sidecar" in low or "rapidocr" in low or "fingerprint" in low:
        return "SK-Q004"
    if "unable to export" in low or "min_scale" in low or "typeset" in low:
        return "SK-Q005"
    if "table" in low or "tbltr" in low or "column" in low or "hpd" in low or "not_a_table" in low:
        if "regulatory" in low or "form" in low or "short_label" in low:
            return "SK-Q003"
        return "SK-Q009"
    if "fallback" in low or "glossary" in low:
        return "SK-Q007"
    if "image" in low or "overlay" in low or "ocr" in low:
        return "SK-Q002"
    if "paragraph" in low or "layout" in low:
        return "SK-Q006"
    return "SK-Q008"


def append_inbox(unmatched: list[str]) -> int:
    if not unmatched:
        return 0
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    if not INBOX.is_file():
        INBOX.write_text("# pitfalls inbox（待归档）\n\n", encoding="utf-8")
    existing = INBOX.read_text(encoding="utf-8")
    added = 0
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with INBOX.open("a", encoding="utf-8") as fh:
        for u in unmatched:
            key = u[:80]
            if key in existing:
                continue
            sk = _suggest_skill(u)
            fh.write(
                f"\n## [待归档] {stamp}\n"
                f"- status: 待归档\n"
                f"- suggested_skill: {sk}\n"
                f"- symptom: (从日志)\n"
                f"- log: `{u}`\n"
            )
            added += 1
            existing += key
    return added


def _archive_inbox(sig_id: str, skill_id: str) -> int:
    """待归档 → 已归档，hook 不再催。"""
    if not INBOX.is_file():
        return 0
    text = INBOX.read_text(encoding="utf-8")
    archived = 0

    def repl(block: str) -> str:
        nonlocal archived
        if "status: 待归档" not in block:
            return block
        if f"suggested_skill: {skill_id}" not in block and "suggested_skill:" in block:
            return block
        archived += 1
        block = block.replace("## [待归档]", f"## [已归档] {sig_id}", 1)
        block = block.replace("- status: 待归档", f"- status: 已归档\n- promoted_as: {sig_id}")
        return block

    parts = re.split(r"(?=## \[)", text)
    out = [repl(p) if p.startswith("## [待归档]") else p for p in parts]
    if archived:
        INBOX.write_text("".join(out), encoding="utf-8")
    return archived


def promote(sig_id: str, skill_id: str, note: str = "") -> None:
    slug = SKILL_DIRS.get(skill_id)
    if not slug:
        raise SystemExit(f"unknown skill {skill_id}")
    pitfalls = ROOT / ".cursor/skills" / slug / "pitfalls.md"
    pitfalls.parent.mkdir(parents=True, exist_ok=True)
    if not pitfalls.is_file():
        pitfalls.write_text(f"# 踩坑（{skill_id}）\n\n", encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"\n{len(pitfalls.read_text(encoding='utf-8').splitlines())}. **{sig_id}（{stamp}）** — {note or 'from capture promote'}\n"
    with pitfalls.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    n = _archive_inbox(sig_id, skill_id)
    # registry audit line
    if REGISTRY.is_file():
        with REGISTRY.open("a", encoding="utf-8") as fh:
            fh.write(f"| {stamp} | promote {sig_id} → {skill_id}（PLAN-047g） |\n")
    print(f"promoted {sig_id} → {skill_id} ({slug}); inbox_archived={n}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, help="journal/作业日志")
    ap.add_argument("--imgtr", type=Path, help="*.imgtr.json")
    ap.add_argument("--verify-out", type=Path, help="verify 脚本输出")
    ap.add_argument("--promote", help="签名 id")
    ap.add_argument("--skill", help="SK-ID")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    if args.promote:
        if not args.skill:
            print("--promote requires --skill", file=sys.stderr)
            return 1
        promote(args.promote, args.skill, args.note)
        return 0

    blobs: list[str] = []
    for path in (args.log, args.verify_out):
        if path and path.is_file():
            blobs.append(path.read_text(encoding="utf-8", errors="replace"))
    if args.imgtr and args.imgtr.is_file():
        try:
            j = json.loads(args.imgtr.read_text(encoding="utf-8"))
            for d in j.get("details") or []:
                qc = d.get("object_qc") or []
                ch = d.get("qc_channel")
                blobs.append(
                    f"imgtr xref={d.get('xref')} blocks={d.get('blocks')} "
                    f"qc_channel={ch} object_qc={qc}"
                )
                if int(d.get("blocks") or 0) > 0 and not qc:
                    blobs.append("QC_CHANNEL_BLIND object_qc: []")
        except Exception as exc:
            blobs.append(f"WARNING imgtr parse failed: {exc}")

    text = "\n".join(blobs)
    if not text.strip():
        # 允许无输入：只验证签名表可读
        sigs = _load_signatures()
        print(f"signatures_loaded={len(sigs)} (no input)")
        return 0

    sigs = _load_signatures()
    hits, unmatched = _scan(text, sigs)
    print("HITS:")
    for k, v in sorted(hits.items()):
        print(f"  {k}: {v}")
    added = append_inbox(unmatched)
    print(f"INBOX_ADDED: {added}")
    print(f"UNMATCHED: {len(unmatched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

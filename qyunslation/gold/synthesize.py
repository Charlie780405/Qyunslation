# SPDX-License-Identifier: MPL-2.0
"""PLAN-034a1：确定性合成金标占位 PDF（PyMuPDF + 固定 /ID）。"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


def _stable_pdf_id(seed: str) -> bytes:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest().upper()
    a, b = digest[:32], digest[32:64]
    return f"/ID[<{a}><{b}>]".encode("ascii")


def write_placeholder_pdf(
    path: Path | str,
    *,
    gold_class: str,
    entry_id: str,
    title: str,
) -> str:
    """写 1 页 A4 占位 PDF；相同参数重复写入哈希不变。返回 sha256 hex。"""
    import pymupdf

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    seed = f"plan034a1|{gold_class}|{entry_id}|{title}"
    doc = pymupdf.open()
    doc.set_metadata(
        {
            "producer": "qyunslation-plan034a1",
            "creator": "qyunslation-plan034a1",
            "title": title,
            "subject": f"PLAN-034a1 {gold_class} {entry_id}",
            "creationDate": "D:20260101000000Z",
            "modDate": "D:20260101000000Z",
        }
    )
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text((72, 100), "PLAN-034a1 gold placeholder", fontsize=14, fontname="helv")
    page.insert_text((72, 130), f"class: {gold_class}", fontsize=11, fontname="helv")
    page.insert_text((72, 150), f"id: {entry_id}", fontsize=11, fontname="helv")
    page.insert_text((72, 180), title[:90], fontsize=12, fontname="helv")
    page.insert_text((72, 800), f"QY-034A1-{entry_id}", fontsize=9, fontname="helv")
    doc.save(
        path.as_posix(),
        garbage=0,
        deflate=False,
        clean=False,
        encryption=pymupdf.PDF_ENCRYPT_NONE,
    )
    doc.close()

    raw = path.read_bytes()
    fixed = re.sub(rb"/ID\s*\[[^\]]*\]", _stable_pdf_id(seed), raw, count=1)
    if fixed == raw and b"/ID[" not in raw:
        raise RuntimeError("synthetic PDF missing /ID trailer; cannot stabilize hash")
    path.write_bytes(fixed)
    return hashlib.sha256(fixed).hexdigest()


def sha256_file(path: Path | str) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()

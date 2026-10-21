# SPDX-License-Identifier: MPL-2.0
"""PLAN-084: 送翻译前的源 PDF 修复（同名副本）与译后收尾。全部 fail-open。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SIDECAR = "dropcaps.json"


def prepare_source(source: Path, workdir: Path) -> Path:
    """符号字体 ToUnicode 修复 → 首字下沉还原。返回要送翻译的 PDF（可能就是 ``source``）。"""
    from qyunslation.structure.pdf_dropcap import normalize_dropcaps
    from qyunslation.structure.pdf_symbol_cmap import prepare_source_pdf

    original = source.resolve()
    current = prepare_source_pdf(source, workdir)
    try:
        target = workdir / source.name
        records = normalize_dropcaps(current, target)
    except Exception:  # noqa: BLE001
        records = []
        target = current
    try:
        sidecar = workdir / SIDECAR
        if records:
            workdir.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(
                json.dumps({"origin": str(original), "records": [r.as_dict() for r in records]}, ensure_ascii=False),
                encoding="utf-8",
            )
        else:
            sidecar.unlink(missing_ok=True)
    except OSError:
        pass
    return target if records else current


def finish_translated_outputs(run_dir: Path, output_dir: Path) -> dict[str, Any] | None:
    """译后：首字下沉的中文首字放大 + 双语左半换回原件页。无记录或任何异常都返回 None/统计，不抛。"""
    try:
        from qyunslation.structure.pdf_dropcap import DropCap, finish_dropcaps

        sidecar = run_dir / "source" / SIDECAR
        if not sidecar.is_file() or not output_dir.is_dir():
            return None
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        records = [DropCap(**item) for item in data.get("records", [])]
        origin = Path(data.get("origin") or "")
        out: dict[str, Any] = {}
        for pdf in sorted(output_dir.glob("*.zh.mono.pdf")):
            out[pdf.name] = finish_dropcaps(pdf, origin, records, dual=False)
        for pdf in sorted(output_dir.glob("*.zh.dual.pdf")):
            out[pdf.name] = finish_dropcaps(pdf, origin, records, dual=True)
        return out
    except Exception:  # noqa: BLE001
        return None

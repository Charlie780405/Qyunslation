# SPDX-License-Identifier: MPL-2.0
"""PLAN-084: 送翻译前的源 PDF 修复（同名副本）与译后收尾。全部 fail-open。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SIDECAR = "dropcaps.json"


def prepare_source(source: Path, workdir: Path) -> Path:
    """符号字体 ToUnicode 修复 → 首字下沉还原 → 横向整页转正。返回要送翻译的 PDF（可能就是 ``source``）。"""
    from qyunslation.structure.pdf_dropcap import normalize_dropcaps
    from qyunslation.structure.pdf_symbol_cmap import prepare_source_pdf

    original = source.resolve()
    current = prepare_source_pdf(source, workdir)
    changed = False
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
    if records:
        current = target
    try:
        from qyunslation.structure.pdf_rotate import normalize_rotated_pages, write_sidecar

        rotated_target = workdir / source.name
        rotated = normalize_rotated_pages(current, rotated_target)
        write_sidecar(workdir, original, rotated)
        if rotated:
            current = rotated_target
    except Exception:  # noqa: BLE001
        pass
    return current


def finish_translated_outputs(run_dir: Path, output_dir: Path) -> dict[str, Any] | None:
    """译后：首字下沉的中文首字放大 + 双语左半换回原件页；横向页转回原方向。任何异常都吞掉。"""
    if not output_dir.is_dir():
        return None
    out: dict[str, Any] = {}
    try:
        from qyunslation.structure.pdf_dropcap import DropCap, finish_dropcaps

        sidecar = run_dir / "source" / SIDECAR
        if sidecar.is_file():
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            records = [DropCap(**item) for item in data.get("records", [])]
            origin = Path(data.get("origin") or "")
            for pdf in sorted(output_dir.glob("*.zh.mono.pdf")):
                out[pdf.name] = finish_dropcaps(pdf, origin, records, dual=False)
            for pdf in sorted(output_dir.glob("*.zh.dual.pdf")):
                out[pdf.name] = finish_dropcaps(pdf, origin, records, dual=True)
    except Exception:  # noqa: BLE001
        pass
    # 转回原方向必须放在最后：上面的处理都按转正后的页面坐标。
    try:
        from qyunslation.structure.pdf_rotate import finish_rotated_pages, read_sidecar

        loaded = read_sidecar(run_dir / "source")
        if loaded is not None:
            origin, rotated = loaded
            for pdf in sorted(output_dir.glob("*.zh.mono.pdf")):
                out[pdf.name + ":rotate"] = finish_rotated_pages(pdf, origin, rotated, dual=False)
            for pdf in sorted(output_dir.glob("*.zh.dual.pdf")):
                out[pdf.name + ":rotate"] = finish_rotated_pages(pdf, origin, rotated, dual=True)
    except Exception:  # noqa: BLE001
        pass
    return out or None

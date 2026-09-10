#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-030-table Task 0：金样矩阵 + 候选栈记录（camelot/tabula 未采纳原因）。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.structure import PdfStructureScanner  # noqa: E402
from qyunslation.structure.models import ObjectType  # noqa: E402

SAMPLES = {
    "ljae439": ROOT / "tests/fixtures/structure/reference/ljae439.pdf",
    "nature": ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf",
}

EXPECTED_TABLES = {
    "ljae439": {5: [1, 2], 7: [3]},
    "nature": {4: [1], 5: [2], 9: [3]},
}


def _camelot_available() -> tuple[bool, str]:
    try:
        import importlib.util

        if importlib.util.find_spec("camelot") is None:
            return False, "camelot not installed"
        return True, "import ok"
    except Exception as exc:
        return False, str(exc)


def _java_available() -> tuple[bool, str]:
    if shutil.which("java"):
        proc = subprocess.run(["java", "-version"], capture_output=True, text=True)
        line = (proc.stderr or proc.stdout).splitlines()[0] if proc else ""
        return proc.returncode == 0, line or "java present"
    return False, "java not installed"


def main() -> int:
    camelot_ok, camelot_detail = _camelot_available()
    java_ok, java_detail = _java_available()
    report: dict = {
        "schema": "plan030-table-task0/v1",
        "candidates": {
            "camelot_py": {"available": camelot_ok, "detail": camelot_detail},
            "tabula_py": {"available": java_ok, "detail": java_detail},
            "in_house_table_structure": {"available": True, "detail": "qyunslation/structure/table_structure.py"},
        },
        "decision": "in_house_table_structure",
        "samples": {},
    }
    failed = False
    for name, path in SAMPLES.items():
        if not path.is_file():
            report["samples"][name] = {"error": "missing fixture"}
            failed = True
            continue
        manifest = PdfStructureScanner().scan(path)
        tables = {
            int(o.semantic_id.split(":")[1]): o
            for o in manifest.objects
            if o.type is ObjectType.TABLE and o.semantic_id
        }
        pages: dict[str, list] = {}
        for page_no, numbers in EXPECTED_TABLES[name].items():
            entries = []
            for num in numbers:
                table = tables.get(num)
                if table is None:
                    entries.append({"number": num, "error": "manifest table missing"})
                    failed = True
                    continue
                rows = table.row_count or 0
                cols = table.column_count or 0
                entries.append(
                    {
                        "number": num,
                        "row_count": rows,
                        "column_count": cols,
                        "recall": rows >= 2 and cols >= 2,
                    }
                )
                if rows < 2 or cols < 2:
                    failed = True
            pages[str(page_no)] = entries
        report["samples"][name] = pages
    out = Path("/tmp/plan030-table-task0.json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    if failed:
        print("TASK0_FAIL: gold sample grid incomplete", file=sys.stderr)
        return 2
    if not report["candidates"]["in_house_table_structure"]["available"]:
        return 2
    print("TASK0_PASS: adopt in-house table_structure (033i), skip camelot/tabula")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

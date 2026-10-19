#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-079 F2：用已上传过的真实源文件评估预检探测的误阻断（只读，只输出聚合）。

``blocked`` 的预检会直接拒绝创建任务（qyunslation/api/v1.py），所以探测对**能正常翻译的文件**
报出阻断项就是误报。默认扫描 var/preflights/ 下已有的上传（它们都通过了当时的预检并成为过任务）。
输出：按格式的文件数、阻断/警告码计数、耗时分布、探测失败数；不输出文件名和正文。

    python3 scripts/qa/plan079_probe_eval.py [--root var/preflights] [--source-language en]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SUFFIXES = {".pdf", ".docx", ".pptx", ".txt", ".md", ".png", ".jpg", ".jpeg"}


def evaluate(files: list[Path], source_language: str | None) -> dict:
    from qyunslation.pipeline.preflight_probe import PROBE_BUDGET_SECONDS, probe_document

    per_format: Counter[str] = Counter()
    blockers: defaultdict[str, Counter[str]] = defaultdict(Counter)
    warnings: Counter[str] = Counter()
    blocked_files: list[dict] = []
    durations: list[float] = []
    probe_failed = over_budget = 0
    for path in files:
        suffix = path.suffix.casefold()
        per_format[suffix] += 1
        started = time.monotonic()
        result = probe_document(path, suffix, source_language)
        elapsed = time.monotonic() - started
        durations.append(elapsed)
        over_budget += elapsed > PROBE_BUDGET_SECONDS + 1.0
        for issue in result.issues:
            if issue["code"] == "PROBE_FAILED":
                probe_failed += 1
            elif issue["severity"] == "blocker":
                blockers[suffix][issue["code"]] += 1
            elif issue["severity"] == "warning":
                warnings[issue["code"]] += 1
        if result.blocked:
            blocked_files.append({"file": path.name[:8], "format": suffix,
                                  "codes": [i["code"] for i in result.issues if i["severity"] == "blocker"]})
    durations.sort()
    pct = lambda q: round(durations[min(len(durations) - 1, int(len(durations) * q))], 3) if durations else 0.0  # noqa: E731
    return {
        "files": len(files),
        "per_format": dict(per_format),
        "blocked": len(blocked_files),
        "blocker_codes_by_format": {k: dict(v) for k, v in blockers.items()},
        "warning_codes": dict(warnings),
        "probe_failed": probe_failed,
        "over_budget": over_budget,
        "seconds": {"p50": pct(0.5), "p95": pct(0.95), "max": round(durations[-1], 3) if durations else 0.0},
        "blocked_files": blocked_files[:30],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PLAN-079 F2 preflight probe false-block evaluation")
    parser.add_argument("--root", default="var/preflights")
    parser.add_argument("--source-language", default=None)
    args = parser.parse_args()
    root = ROOT / args.root
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.casefold() in SUFFIXES)
    print(json.dumps(evaluate(files, args.source_language), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

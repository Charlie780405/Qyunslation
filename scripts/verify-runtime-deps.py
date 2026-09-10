#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-030ic：对照 versions-030.lock 验证运行环境。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.structure.runtime_probe import (  # noqa: E402
    probe_babeldoc_layout,
    probe_image_decoders,
    probe_office,
    probe_version_contract,
)


def main() -> int:
    probes = [
        probe_version_contract(),
        probe_office(),
        probe_babeldoc_layout(),
        probe_image_decoders(),
    ]
    failed = False
    for item in probes:
        status = "ok" if item.ok else "FAIL"
        print(f"{status}\t{item.name}\t{item.reason}")
        for key, value in sorted(item.versions.items()):
            print(f"  {key}={value}")
        if not item.ok:
            failed = True
    if failed:
        print("DEPLOY_STOP: runtime dependency contract mismatch", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

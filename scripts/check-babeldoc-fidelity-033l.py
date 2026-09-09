#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""生产部署前：BabelDOC 版本与 033h 补丁签名自检。不匹配则停止部署。"""
from __future__ import annotations

import sys

from qyunslation.structure.plan033_final import babeldoc_version, patch_signature

REQUIRED_MARKERS = ("il", "terms", "creater", "fontmap")


def main() -> int:
    version = babeldoc_version()
    sigs = patch_signature()
    print(f"babeldoc={version or 'unknown'}")
    failed = False
    for name in REQUIRED_MARKERS:
        value = sigs.get(name, "missing")
        marked = value.endswith(":1")
        print(f"patch {name}={value}")
        if value == "missing" or not marked:
            failed = True
    if failed:
        print("DEPLOY_STOP: BabelDOC patch signature mismatch", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

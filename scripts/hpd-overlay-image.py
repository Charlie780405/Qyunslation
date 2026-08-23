#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-005c CLI：HPD + 35b 图片嵌字。用法: hpd-overlay-image.py in.png out.png"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qyunslation.extensions.image_translate import translate_image  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: hpd-overlay-image.py in.png out.png", file=sys.stderr)
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    t0 = time.time()
    n = translate_image(src, dst)
    print(f"overlay blocks={n} -> {dst} ({time.time() - t0:.1f}s)")
    return 0 if n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

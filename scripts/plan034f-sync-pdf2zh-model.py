#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-034f：将 quality 档 model_id 投影到 pdf2zh env/toml 片段（不写密钥）。

用法::

    .venv/bin/python scripts/plan034f-sync-pdf2zh-model.py
    .venv/bin/python scripts/plan034f-sync-pdf2zh-model.py --write /tmp/pdf2zh-model.env

默认只打印；``--write`` 写出 ``KEY=value`` 行。不重启 pdf2zh，不改进程内循环。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync gateway quality model to pdf2zh env fragment")
    parser.add_argument("--profile", default="quality")
    parser.add_argument("--write", type=Path, default=None, help="optional output path")
    args = parser.parse_args()

    from qyunslation.gateway.config import ProfileNotWiredError, resolve_profile

    try:
        resolved = resolve_profile(args.profile)
    except ProfileNotWiredError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    lines = [
        f"# PLAN-034f gateway profile={resolved['profile']} (no secrets)",
        f"QYUNSLATION_MODEL_ID={resolved['model_id']}",
        f"DOCUTRANSLATE_MODEL_ID={resolved['model_id']}",
        # endpoint 仅当环境已有时回显剥离后的值，脚本不写入新密钥
    ]
    if resolved.get("endpoint_stripped"):
        lines.append(f"# endpoint_stripped={resolved['endpoint_stripped']}")
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if args.write:
        args.write.write_text(text, encoding="utf-8")
        print(f"# wrote {args.write}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

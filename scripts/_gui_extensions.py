#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-030h H2：apply-pdf2zh-*.py 共用的 GUI 扩展名清单渲染。

补丁脚本注入的代码运行在 pdf2zh 进程里，那里没有 qyunslation 包，所以扩展名
必须在**打补丁时**渲染成字面量。此前六处补丁各自手写集合，`capabilities.py`
已登记为 CORE 的 WebP/BMP/TIFF 在文件选择器里选不了。

清单不可用时直接退出：宁可服务起不来，也不要静默回退到过期的硬编码集合。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from qyunslation.structure.capabilities import (
        gui_extension_manifest,
        gui_image_mime_types,
    )
except Exception as exc:  # pragma: no cover - 由 systemd 报错暴露
    raise SystemExit(
        f"FATAL: 无法载入格式能力清单，拒绝用过期字面量打补丁：{exc}"
    ) from exc

MANIFEST = gui_extension_manifest()


def extensions(key: str, *, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    values = MANIFEST[key]
    return tuple(sorted({*values, *extra}))


def set_literal(key: str, *, extra: tuple[str, ...] = ()) -> str:
    """渲染成 Python 集合字面量，如 ``{".bmp", ".jpg"}``。"""
    items = ", ".join(f'"{ext}"' for ext in extensions(key, extra=extra))
    return "{" + items + "}"


def list_literal(key: str, *, extra: tuple[str, ...] = ()) -> str:
    """渲染成 Python 列表字面量，如 ``[".bmp", ".jpg"]``。"""
    items = ", ".join(f'"{ext}"' for ext in extensions(key, extra=extra))
    return "[" + items + "]"


def image_mime_literal() -> str:
    """渲染扩展名到 MIME 的映射字面量，供预览分支使用。"""
    pairs = ", ".join(
        f'"{ext}": "{mime}"' for ext, mime in sorted(gui_image_mime_types().items())
    )
    return "{" + pairs + "}"


if __name__ == "__main__":
    for name in sorted(MANIFEST):
        print(f"{name}: {list_literal(name)}")

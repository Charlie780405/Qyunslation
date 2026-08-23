#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""把 pdf2zh Gradio 白牌成 Qyunslation（荃信翻译）。uv 升级后重跑。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
BRAND_DIR = Path("/home/dev/pdf2zh/brand")
LOGO = BRAND_DIR / "quanxin-logo.svg"
TABLE_LOGO = Path("/home/dev/qyunsgen/public/brands/quanxin-biopharma.svg")
MARKER = "qy-brand"


def _ensure_logo() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    if TABLE_LOGO.is_file():
        shutil.copy2(TABLE_LOGO, LOGO)


def _header_html() -> str:
    return (
        f'<div class="{MARKER}">'
        f'<img src="/gradio_api/file={LOGO}" alt="QYuns">'
        "<div><strong>Qyunslation</strong><span>荃信翻译</span></div>"
        "</div>"
    )


def _footer_html() -> str:
    return (
        f'<div class="{MARKER} {MARKER}-footer">'
        f'<img src="/gradio_api/file={LOGO}" alt="QYuns">'
        "<span>Qyunslation@荃信生物</span>"
        "</div>"
    )


def apply(text: str) -> str:
    header = (
        "        gr.HTML(\n"
        f"            {_header_html()!r}\n"
        "        )\n"
    )
    footer = (
        "                    tech_details = gr.HTML(\n"
        f"                        {_footer_html()!r},\n"
        "                    )\n"
    )

    text = text.replace(
        'title="PDFMathTranslate - PDF Translation with preserved formats"',
        'title="Qyunslation · 荃信翻译"',
    )
    text = text.replace(
        '        gr.Markdown("# [PDFMathTranslate Next](https://pdf2zh-next.com)")\n',
        header,
    )

    # 已打过旧白牌：整段替换 header / footer HTML
    if 'class="qy-brand"' in text:
        import re

        text = re.sub(
            r"        gr\.HTML\(\n            '<div class=\"qy-brand\">.*?</div>'\n        \)\n",
            header,
            text,
            count=1,
            flags=re.DOTALL,
        )
        text = re.sub(
            r"                    tech_details = gr\.HTML\(\n                        '<div class=\"qy-brand qy-brand-footer\">.*?</div>',\n                    \)\n",
            footer,
            text,
            count=1,
            flags=re.DOTALL,
        )

    text = text.replace(
        "                    tech_details = gr.Markdown(\n"
        "                        tech_details_string,\n"
        '                        elem_classes=["secondary-text"],\n'
        "                    )\n",
        footer,
    )
    text = text.replace(
        '                    siliconflow_free_acknowledgement = gr.Markdown(\n'
        '                        _(\n'
        '                            "Free translation service provided by [SiliconFlow](https://siliconflow.cn)"\n'
        '                        ),\n'
        '                        visible=True,\n'
        '                    )',
        '                    siliconflow_free_acknowledgement = gr.Markdown(\n'
        '                        _(\n'
        '                            "Free translation service provided by [SiliconFlow](https://siliconflow.cn)"\n'
        '                        ),\n'
        '                        visible=False,\n'
        '                    )',
    )

    if "brand_logo_path" not in text:
        text = text.replace(
            'logo_path = assets_dir / "powered_by_siliconflow_light.png"\n',
            'logo_path = assets_dir / "powered_by_siliconflow_light.png"\n'
            f"BRAND_DIR = Path({str(BRAND_DIR)!r})\n"
            'brand_logo_path = BRAND_DIR / "quanxin-logo.svg"\n',
        )
        text = text.replace(
            "    logo_path,\n    Path(\"pdf2zh_files\").resolve(),",
            "    logo_path,\n    brand_logo_path,\n    BRAND_DIR,\n"
            "    Path(\"pdf2zh_files\").resolve(),",
        )
    else:
        text = text.replace(
            'brand_logo_path = BRAND_DIR / "qyunslation.png"',
            'brand_logo_path = BRAND_DIR / "quanxin-logo.svg"',
        )

    old_css_start = "    .qy-brand {"
    brand_css = """    .qy-brand {
        display: flex;
        align-items: center;
        gap: 14px;
        margin: 4px 0 14px;
    }
    .qy-brand img {
        height: 40px;
        width: auto;
        max-width: 220px;
        object-fit: contain;
        object-position: left center;
        background: transparent;
        border-radius: 0;
    }
    .qy-brand strong {
        display: block;
        font-size: 1.35rem;
        line-height: 1.2;
        color: #0f172a;
    }
    .qy-brand span {
        display: block;
        color: #64748b;
        font-size: 0.92rem;
    }
    .qy-brand-footer {
        margin: 16px 0 4px;
        justify-content: center;
    }
    .qy-brand-footer img {
        height: 32px;
        max-width: 180px;
    }
    .qy-brand-footer span {
        display: inline;
        color: #475569;
        font-size: 0.95rem;
    }
"""
    if old_css_start in text:
        import re

        text = re.sub(
            r"    \.qy-brand \{.*?\n    \.qy-brand-footer span \{.*?\n    \}\n",
            brand_css,
            text,
            count=1,
            flags=re.DOTALL,
        )
    else:
        marker = "    /* SiliconFlow logo:"
        if marker in text:
            text = text.replace(marker, brand_css + "\n    /* SiliconFlow logo:", 1)
        else:
            text = text.replace(
                '    .lang-swap-btn:active {\n        background: rgba(148, 163, 184, 0.2) !important;\n    }\n    """',
                '    .lang-swap-btn:active {\n        background: rgba(148, 163, 184, 0.2) !important;\n    }\n'
                + brand_css
                + '    """',
                1,
            )
    return text


def main() -> int:
    _ensure_logo()
    if not GUI.is_file():
        print(f"找不到 {GUI}", file=sys.stderr)
        return 1
    if not LOGO.is_file():
        print(f"找不到 logo {LOGO}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    updated = apply(original)
    if updated == original:
        print("已是荃信字标白牌，无需再改")
        return 0
    GUI.write_text(updated, encoding="utf-8")
    print(f"已写入 {GUI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-080a：逐页诊断 PDF 译文的漏译、字体与装饰线（只读）。

    .venv/bin/python -I scripts/qa/plan080_diagnose.py SOURCE.pdf OUTPUT.pdf \
        [--label NAME] [--manifest manifest.json]

回答 PLAN-080 §2.2 的几个问题：

* 长段落（≥40 个非空白字符、不含汉字）中，译文里有多少与源文逐字相同（即"送了但结果等于源文"
  或"根本没送翻译"，两者在输出里都表现为原样保留）。
* 原样保留的段落使用什么字体（H1：是否被公式字体判定吞掉，字体名会出现在这里）。
* 页面上的字体族与字号种类（C2 基线）。
* 水平细线（下划线候选）与其下方文本行的宽度关系，以及找不到归属的悬空线（C3 / H5 基线）。

只输出聚合数字与截断到 60 字符的摘录；不把整页正文写入结果。结果写入 var/plan080/<label>.json（不入库）。
不读取 .env，不访问数据库，不修改输入文件。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "var" / "plan080"

CJK = re.compile(r"[一-鿿]")
LONG_CHARS = 40            # 长段落阈值（去空白后的字符数）
TITLE_MAX_CHARS = 200      # 人名/职务启发式只用于短块，避免把正文误判为名单
DECOR_MAX_THICKNESS = 1.5  # pt，水平线的最大高度
DECOR_MIN_WIDTH = 5.0      # pt，短于此的线视为项目符号/页码装饰，不计
LONG_RATIO = 1.3           # 下划线宽度 / 文字宽度 超过此值记为"过长"
TITLE_HINT = re.compile(
    r"Director|Officer|Manager|Office of|Division|Deputy|Chief|Team Leader|"
    r"Pharmacokineticist|Statistic|Biostatistic|Reviewer|Scientist|Coordinator|"
    r", MD\b|, PhD\b|, PharmD\b",
    re.IGNORECASE,
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def split_font(name: str) -> tuple[str, str]:
    """'ABCDEF+Arial-ItalicMT' -> ('Arial', 'ItalicMT')。"""
    name = re.sub(r"^[A-Z]{6}\+", "", name)
    parts = re.split(r"[-,]", name, maxsplit=1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def page_blocks(page: pymupdf.Page) -> list[dict]:
    """文本块（段落的近似）：文字、坐标、字体与字号。"""
    blocks = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        spans = [sp for line in block["lines"] for sp in line["spans"] if sp["text"].strip()]
        if not spans:
            continue
        text = norm("".join(sp["text"] for line in block["lines"] for sp in line["spans"]))
        blocks.append(
            {
                "text": text,
                "compact": compact(text),
                "bbox": block["bbox"],
                "fonts": [(sp["font"], round(sp["size"], 1)) for sp in spans],
            }
        )
    return blocks


def page_lines(page: pymupdf.Page) -> list[dict]:
    """文本行：下划线的归属以行为单位，避免多行段落把整段当作一条线的承接对象。"""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            text = norm("".join(sp["text"] for sp in line["spans"]))
            if text:
                lines.append({"text": text, "bbox": line["bbox"], "cjk": bool(CJK.search(text))})
    return lines


def thin_lines(page: pymupdf.Page) -> list[dict]:
    lines = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.height <= DECOR_MAX_THICKNESS and rect.width >= DECOR_MIN_WIDTH:
            lines.append({"x0": rect.x0, "x1": rect.x1, "y": rect.y0, "width": rect.width})
    return lines


def match_underlines(lines: list[dict], text_lines: list[dict]) -> list[dict]:
    """把每条水平线对应到它所在的文本行。

    归属条件：线的纵坐标落在文本行纵向范围内或紧贴其下沿（3pt 内），且横向重叠至少为
    两者较短一方的 50%。取横向重叠最大的文本行。找不到归属的线记为悬空。
    """
    results = []
    for line in lines:
        best, best_overlap = None, 0.0
        for text_line in text_lines:
            x0, y0, x1, y1 = text_line["bbox"]
            if not (y0 - 1.0 <= line["y"] <= y1 + 3.0):
                continue
            overlap = min(line["x1"], x1) - max(line["x0"], x0)
            if overlap <= 0.5 * min(line["width"], x1 - x0):
                continue
            if overlap > best_overlap:
                best, best_overlap = text_line, overlap
        if best is None:
            results.append({"matched": False, "width": round(line["width"], 1)})
            continue
        text_width = best["bbox"][2] - best["bbox"][0]
        results.append(
            {
                "matched": True,
                "cjk": best["cjk"],
                "width": round(line["width"], 1),
                "text_width": round(text_width, 1),
                "ratio": round(line["width"] / max(text_width, 1e-6), 2),
                "text": best["text"][:60],
            }
        )
    return results


def analyse_page(src_page: pymupdf.Page, out_page: pymupdf.Page) -> dict:
    src_blocks = page_blocks(src_page)
    out_blocks = page_blocks(out_page)
    src_compact_page = "".join(b["compact"] for b in src_blocks)

    src_long = [b for b in src_blocks if len(b["compact"]) >= LONG_CHARS and not CJK.search(b["text"])]

    kept, translated, reworded = [], 0, 0
    for block in out_blocks:
        if CJK.search(block["text"]):
            translated += 1
            continue
        if len(block["compact"]) < LONG_CHARS:
            continue
        if block["compact"] in src_compact_page:
            fonts = Counter(split_font(f)[0] for f, _ in block["fonts"])
            kept.append(
                {
                    "text": block["text"][:60],
                    "chars": len(block["compact"]),
                    "font_families": dict(fonts),
                    "title_like": len(block["compact"]) < TITLE_MAX_CHARS and bool(TITLE_HINT.search(block["text"])),
                }
            )
        else:
            reworded += 1

    src_fam, out_fam = Counter(), Counter()
    for block in src_blocks:
        for font, _ in block["fonts"]:
            fam, style = split_font(font)
            src_fam[f"{fam}/{style}"] += 1
    for block in out_blocks:
        for font, size in block["fonts"]:
            if size < 7:  # 页脚、脚注标记不计入正文字体基线
                continue
            fam, style = split_font(font)
            out_fam[f"{fam}/{style}"] += 1

    src_under = match_underlines(thin_lines(src_page), page_lines(src_page))
    out_under = match_underlines(thin_lines(out_page), page_lines(out_page))

    return {
        "src_long_blocks": len(src_long),
        "out_translated_blocks": translated,
        "out_kept_as_source_blocks": len(kept),
        "out_kept_as_source_chars": sum(k["chars"] for k in kept),
        "out_reworded_not_in_source_blocks": reworded,
        "kept_title_like": sum(1 for k in kept if k["title_like"]),
        "kept_samples": kept[:12],
        "src_font_families": dict(src_fam.most_common(10)),
        "out_font_families": dict(out_fam.most_common(10)),
        "out_font_family_count": len(out_fam),
        "src_underlines": src_under,
        "out_underlines": out_under,
    }


def content_profile(manifest_path: Path | None) -> dict:
    if manifest_path is None or not manifest_path.is_file():
        return {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc = data.get("document", {})
    return {
        "content_profile": doc.get("content_profile"),
        "profile_confidence": doc.get("profile_confidence"),
        "selected_mode": doc.get("selected_mode"),
    }


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def summarise(pages: list[dict]) -> dict:
    total_src_long = sum(p["src_long_blocks"] for p in pages)
    total_kept = sum(p["out_kept_as_source_blocks"] for p in pages)
    under_out = [u for p in pages for u in p["out_underlines"] if u["matched"]]
    under_src = [u for p in pages for u in p["src_underlines"] if u["matched"]]
    cjk_out = [u["ratio"] for u in under_out if u["cjk"]]
    latin_out = [u["ratio"] for u in under_out if not u["cjk"]]
    latin_src = [u["ratio"] for u in under_src if not u["cjk"]]
    return {
        "pages": len(pages),
        "src_long_blocks": total_src_long,
        "kept_as_source_blocks": total_kept,
        "kept_title_like": sum(p["kept_title_like"] for p in pages),
        "kept_non_title_blocks": total_kept - sum(p["kept_title_like"] for p in pages),
        "font_family_max_per_page": max((p["out_font_family_count"] for p in pages), default=0),
        "underline_src_matched": len(under_src),
        "underline_src_orphan": sum(1 for p in pages for u in p["src_underlines"] if not u["matched"]),
        "underline_src_ratio_median_latin": _median(latin_src),
        "underline_out_matched_cjk": len(cjk_out),
        "underline_out_ratio_median_cjk": _median(cjk_out),
        "underline_out_over_limit_cjk": sum(1 for r in cjk_out if r > LONG_RATIO),
        "underline_out_matched_latin": len(latin_out),
        "underline_out_over_limit_latin": sum(1 for r in latin_out if r > LONG_RATIO),
        "underline_out_orphan": sum(1 for p in pages for u in p["out_underlines"] if not u["matched"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--label", default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args(argv)

    src = pymupdf.open(args.source)
    out = pymupdf.open(args.output)
    if len(src) != len(out):
        print(f"page count differs: source={len(src)} output={len(out)}", file=sys.stderr)

    pages = []
    for index in range(min(len(src), len(out))):
        info = analyse_page(src[index], out[index])
        info["page"] = index + 1
        pages.append(info)

    label = args.label or args.output.stem
    result = {
        "label": label,
        "source": args.source.name,
        "output": args.output.name,
        **content_profile(args.manifest),
        "summary": summarise(pages),
        "pages": pages,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / f"{re.sub(r'[^A-Za-z0-9._-]+', '_', label)}.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-080b：汇总 `plan080_trace_run.py` 的追踪文件，列出每个段落的最终去向。

    python3 scripts/qa/plan080_trace_report.py TRACE.jsonl [--json OUT.json]

去向分类（按优先级）：

* skipped:<reason>   被谓词排除（preserve / cid / numeric / placeholder / target_lang）
* translated         LLM 结果写回且与送出文本不同
* unchanged          写回了但与送出文本相同（原样返回）
* fallback_unchanged 走了普通翻译回退，写回的仍与送出文本相同
* fallback_no_result 走了普通翻译回退，没有写回记录
* not_sent           看到了但没有被排除，也没有送出（例如长度低于 min_text_length）
* sent_no_result     送出了但没有写回记录

段落 ID 在同一页内唯一；跨页统计用 (page, id)。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def classify(rows: dict) -> str:
    skips = rows.get("skip", [])
    results = rows.get("result", [])
    if skips and not rows.get("sent"):
        return "skipped:" + skips[0]["reason"]
    if rows.get("fallback"):
        if any(not r["same"] for r in results):
            return "translated"
        return "fallback_unchanged" if results else "fallback_no_result"
    if rows.get("sent"):
        if not results:
            return "sent_no_result"
        return "translated" if any(not r["same"] for r in results) else "unchanged"
    return "not_sent"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    events = [json.loads(line) for line in args.trace.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for event in events:
        key = str(event.get("id"))
        if event["event"] == "seen":
            by_id[key]["seen"].append(event)
        else:
            by_id[key][event["event"]].append(event)

    # 按文本排除的谓词（preserve、target_lang）拿不到段落 ID，按节选文字关联回段落。
    skips_by_text: dict[str, list[dict]] = defaultdict(list)
    for event in by_id.get("None", {}).get("skip", []):
        skips_by_text[event["text"]].append(event)

    rows = []
    for key, grouped in by_id.items():
        if not grouped.get("seen"):
            continue
        seen = grouped["seen"][0]
        if not grouped.get("skip") and not grouped.get("sent") and skips_by_text.get(seen["text"]):
            grouped["skip"] = skips_by_text[seen["text"]]
        rows.append(
            {
                "page": seen.get("page"),
                "id": key,
                "length": seen["length"],
                "fate": classify(grouped),
                "text": seen["text"],
            }
        )
    rows.sort(key=lambda r: (r["page"] or 0, r["id"]))

    counts = Counter(r["fate"] for r in rows)
    print(f"paragraphs seen: {len(rows)}")
    for fate, count in counts.most_common():
        print(f"  {fate:24s} {count}")
    print("\nnot translated and length >= 60 (candidates for UNTRANSLATED_BODY):")
    for row in rows:
        if row["fate"] != "translated" and row["length"] >= 60:
            print(f"  p{row['page']} id={row['id']} len={row['length']:4d} {row['fate']:22s} {row['text'][:60]}")

    if args.json:
        args.json.write_text(json.dumps({"counts": counts, "paragraphs": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

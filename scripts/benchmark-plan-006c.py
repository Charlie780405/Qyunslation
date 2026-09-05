#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-006c：并发拐点 + CHUNK_SIZE JSON 完整性回归。"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import httpx

try:
    from json_repair import json_repair
except ImportError:
    import json as json_repair  # type: ignore

DEFAULT_BASE = "http://100.67.66.123:11434/v1"
DEFAULT_MODEL = "qwen3.6:35b-a3b"
SYS = "You are a professional, authentic machine translation engine."

MED_SEGS = [
    "Atopic dermatitis (AD) is a chronic, relapsing inflammatory skin disease characterized by intense pruritus.",
    "The primary endpoint was the proportion of subjects achieving EASI-75 at Week 16.",
    "Subjects received QX027N 300 mg subcutaneously every two weeks (Q2W) after a loading dose.",
    "Treatment-emergent adverse events (TEAEs) were monitored throughout the study period.",
    "IGA 0/1 response with a reduction of at least 2 points from baseline was assessed as a key secondary endpoint.",
    "The pharmacokinetic profile demonstrated dose-proportional exposure across the tested range.",
    "Peak Pruritus NRS improvement of >=4 points was observed in 52.3% of subjects (p<0.001).",
    "TSLP and IL-13 are key upstream drivers of type 2 inflammation.",
    "Written informed consent was obtained from all participants prior to any study procedure.",
    "Data were analyzed using the full analysis set (FAS) with multiple imputation for missing values.",
    "Dose-limiting toxicity was not observed in any cohort during the dose-escalation phase.",
    "The study was conducted in accordance with the Declaration of Helsinki and ICH-GCP guidelines.",
    "Serum biomarkers including TARC/CCL17 and total IgE were measured at each visit.",
    "Investigator's Global Assessment (IGA) was performed by the same evaluator whenever possible.",
    "Rescue medication use was permitted after Week 4 and recorded as a censoring event.",
    "The safety analysis set included all subjects who received at least one dose of study drug.",
    "Baseline demographics were balanced between the treatment and placebo arms.",
    "Injection site reactions were mild to moderate and resolved without intervention.",
    "DLQI total score change from baseline was analyzed by MMRM.",
    "No deaths or treatment-related serious adverse events were reported.",
]


def build_prompt(segs: dict[str, str]) -> str:
    payload = json.dumps(segs, ensure_ascii=False)
    return f"""
You will receive a sequence of original text segments to be translated, represented in JSON format.
<input>
```json
{payload}
```
</input>
For each Key-Value Pair, translate the value into 中文. Output format: [{{"id":"3","t":"translated 3"}}]
Note: Use "id" for the segment ID and "t" for the translated text. All input IDs must appear in output.
Return the translated JSON directly without any additional information.
"""


def parse_ids(content: str) -> set[str]:
    cleaned = re.sub(r"^```json|```$", "", content.strip(), flags=re.M).strip()
    parsed = json_repair.loads(cleaned)
    if isinstance(parsed, list):
        return {str(x.get("id")) for x in parsed if isinstance(x, dict)}
    if isinstance(parsed, dict):
        return set(map(str, parsed.keys()))
    return set()


async def one_chat(
    client: httpx.AsyncClient, base: str, model: str, segs: dict[str, str]
) -> tuple[float, bool, int]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYS},
            {"role": "user", "content": build_prompt(segs)},
        ],
        "temperature": 0.3,
        "reasoning_effort": "none",
    }
    t0 = time.perf_counter()
    resp = await client.post(
        f"{base}/chat/completions",
        json=body,
        headers={"Authorization": "Bearer ollama"},
        timeout=300.0,
    )
    dt = time.perf_counter() - t0
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    ids = parse_ids(content)
    ok = ids == set(segs.keys())
    toks = data.get("usage", {}).get("completion_tokens", 0)
    return dt, ok, toks


async def run_concurrency(base: str, model: str, levels: list[int]) -> list[dict]:
    segs = {str(i): MED_SEGS[i % len(MED_SEGS)] for i in range(12)}
    rows = []
    for n in levels:
        limits = httpx.Limits(max_connections=n + 5)
        async with httpx.AsyncClient(verify=False, limits=limits) as client:
            t0 = time.perf_counter()
            results = await asyncio.gather(
                *[one_chat(client, base, model, segs) for _ in range(n)]
            )
            wall = time.perf_counter() - t0
        lats = [r[0] for r in results]
        ok = sum(1 for r in results if r[1])
        toks = sum(r[2] for r in results)
        rows.append(
            {
                "concurrency": n,
                "wall_s": round(wall, 2),
                "ok": ok,
                "n": n,
                "lat_min": round(min(lats), 2),
                "lat_med": round(sorted(lats)[len(lats) // 2], 2),
                "lat_max": round(max(lats), 2),
                "tok_per_s": round(toks / wall, 1) if wall else 0,
            }
        )
        print(
            f"并发{n:>3}: wall={wall:6.1f}s ok={ok}/{n} "
            f"med={rows[-1]['lat_med']}s tok/s={rows[-1]['tok_per_s']}"
        )
    return rows


async def run_chunk_integrity(base: str, model: str, sizes: list[int]) -> list[dict]:
    rows = []
    for target_bytes in sizes:
        segs: dict[str, str] = {}
        i = 0
        while True:
            segs[str(i)] = MED_SEGS[i % len(MED_SEGS)]
            payload = json.dumps(segs, ensure_ascii=False)
            if len(payload.encode()) >= target_bytes:
                break
            i += 1
            if i > 200:
                break
        async with httpx.AsyncClient(verify=False) as client:
            dt, ok, toks = await one_chat(client, base, model, segs)
        rows.append(
            {
                "target_chunk_bytes": target_bytes,
                "actual_bytes": len(json.dumps(segs, ensure_ascii=False).encode()),
                "n_segs": len(segs),
                "ok": ok,
                "latency_s": round(dt, 2),
                "completion_tokens": toks,
            }
        )
        print(
            f"chunk~{target_bytes}: segs={len(segs)} bytes={rows[-1]['actual_bytes']} "
            f"ok={ok} {dt:.1f}s"
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out", default="docs/perf/baseline-006c.json")
    ap.add_argument("--skip-concurrency", action="store_true")
    args = ap.parse_args()

    conc = []
    if not args.skip_concurrency:
        conc = asyncio.run(run_concurrency(args.base, args.model, [1, 4, 8, 16]))
    chunks = asyncio.run(run_chunk_integrity(args.base, args.model, [4000, 8000]))

    recommend_chunk = 4000
    for row in chunks:
        if row["target_chunk_bytes"] == 8000 and row["ok"]:
            recommend_chunk = 8000

    out = {
        "plan": "PLAN-006c",
        "model": args.model,
        "base": args.base,
        "concurrency": conc,
        "chunk_integrity": chunks,
        "recommend": {
            "DOCUTRANSLATE_CONCURRENT": 8,
            "DOCUTRANSLATE_TIMEOUT": 300,
            "DOCUTRANSLATE_CHUNK_SIZE": recommend_chunk,
            "note": "CHUNK_SIZE=8000 only if integrity ok; else keep 4000",
        },
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path} recommend_chunk={recommend_chunk}")


if __name__ == "__main__":
    main()

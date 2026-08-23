#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-003b：泰州 Ollama qwen3.6:35b-a3b 翻译段并发曲线。"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

DEFAULT_HOST = "http://100.67.66.123:11434"
DEFAULT_MODEL = "qwen3.6:35b-a3b"
SYSTEM = "/no_think You are a professional, authentic machine translation engine."
SAMPLE = (
    "Translate the following paragraph to Simplified Chinese. "
    "Preserve medical terminology accurately.\n\n"
    "QX027N is a fully human monoclonal antibody targeting IL-17A for the "
    "treatment of moderate-to-severe plaque psoriasis. The phase II study "
    "evaluates efficacy, safety, and pharmacokinetics in adult patients "
    "with inadequate response to conventional therapy."
)


async def one_generate(client: httpx.AsyncClient, host: str, model: str) -> float:
    t0 = time.perf_counter()
    resp = await client.post(
        f"{host}/api/generate",
        json={
            "model": model,
            "prompt": SAMPLE,
            "system": SYSTEM,
            "stream": False,
            "options": {"num_predict": 512},
        },
        timeout=300.0,
    )
    resp.raise_for_status()
    return time.perf_counter() - t0


async def bench_concurrent(host: str, model: str, n: int) -> dict:
    async with httpx.AsyncClient() as client:
        t0 = time.perf_counter()
        results = await asyncio.gather(
            *[one_generate(client, host, model) for _ in range(n)],
            return_exceptions=True,
        )
        wall = time.perf_counter() - t0
    ok = [r for r in results if isinstance(r, float)]
    errs = [str(r) for r in results if not isinstance(r, float)]
    return {
        "concurrent": n,
        "wall_s": round(wall, 2),
        "ok": len(ok),
        "errors": len(errs),
        "avg_latency_s": round(sum(ok) / len(ok), 2) if ok else None,
        "per_request_wall_s": round(wall / len(ok), 2) if ok else None,
        "error_samples": errs[:2],
    }


async def main_async(host: str, model: str, levels: list[int]) -> dict:
    # Warmup
    async with httpx.AsyncClient() as client:
        await one_generate(client, host, model)
    rows = []
    for n in levels:
        rows.append(await bench_concurrent(host, model, n))
        await asyncio.sleep(2)
    best = min(
        (r for r in rows if r["ok"] == r["concurrent"]),
        key=lambda r: r["per_request_wall_s"] or 999,
        default=None,
    )
    rec_parallel = 2
    if best:
        rec_parallel = best["concurrent"]
        if rec_parallel > 4:
            rec_parallel = 4
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": host,
        "model": model,
        "prompt_chars": len(SAMPLE),
        "results": rows,
        "recommended_ollama_num_parallel": rec_parallel,
        "recommended_pdf2zh_qps": rec_parallel if rec_parallel <= 4 else 2,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--levels", default="1,2,4")
    parser.add_argument(
        "--out",
        default=str(
            Path(__file__).resolve().parents[1] / "docs/perf/baseline-003b.json"
        ),
    )
    args = parser.parse_args()
    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    report = asyncio.run(main_async(args.host, args.model, levels))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

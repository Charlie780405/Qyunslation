# SPDX-License-Identifier: MPL-2.0
"""PLAN-033e：进度文案用图/表语义计数，不用内部 OCR 步数。"""
from __future__ import annotations


def format_semantic_progress(
    figures_done: int,
    figures_total: int,
    tables_done: int,
    tables_total: int,
) -> str:
    return (
        f"已处理 图 {max(0, figures_done)}/{max(0, figures_total)} · "
        f"表 {max(0, tables_done)}/{max(0, tables_total)}"
    )


def format_from_manifest(manifest, cur: int, total: int) -> str:
    fig_n = int(getattr(getattr(manifest, "summary", None), "figure_count", 0) or 0)
    tab_n = int(getattr(getattr(manifest, "summary", None), "table_count", 0) or 0)
    if total <= 0:
        done_f = done_t = 0
    else:
        frac = max(0.0, min(1.0, cur / total))
        done_f = min(fig_n, int(round(frac * fig_n)))
        done_t = min(tab_n, int(round(frac * tab_n)))
    return format_semantic_progress(done_f, fig_n, done_t, tab_n)

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


def format_from_execution(manifest) -> str | None:
    objects = list(getattr(manifest, "objects", None) or [])
    if not objects:
        return None
    figures = [obj for obj in objects if str(getattr(obj, "type", "")).endswith("FIGURE") or str(getattr(getattr(obj, "type", None), "name", "")).casefold() == "figure"]
    tables = [obj for obj in objects if str(getattr(getattr(obj, "type", None), "name", "")).casefold() == "table"]
    if not figures and not tables:
        return None

    def _done(items) -> int:
        count = 0
        for obj in items:
            raw = getattr(obj, "execution_status", None)
            name = str(getattr(raw, "name", raw) or "").casefold()
            if name and name not in {"pending", "executionstatus.pending"}:
                count += 1
        return count

    return format_semantic_progress(_done(figures), len(figures), _done(tables), len(tables))


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

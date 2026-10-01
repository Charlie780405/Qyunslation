# SPDX-License-Identifier: MPL-2.0
"""PLAN-071c：表格翻译阶段薄封装。"""
from __future__ import annotations

from qyunslation.pipeline.stages.postprocess import (
    run_table_figure_stage,
    table_overflow_fallback_chain,
)

__all__ = ["run_table_figure_stage", "table_overflow_fallback_chain"]

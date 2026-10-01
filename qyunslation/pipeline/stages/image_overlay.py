# SPDX-License-Identifier: MPL-2.0
"""PLAN-071c：嵌图翻译阶段薄封装。"""
from __future__ import annotations

from qyunslation.pipeline.stages.postprocess import (
    low_confidence_image_policy,
    run_table_figure_stage,
)

__all__ = ["low_confidence_image_policy", "run_table_figure_stage"]

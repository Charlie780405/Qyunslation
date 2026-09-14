# SPDX-License-Identifier: MPL-2.0
"""PLAN-050：Gradio 工作台 UI 适配（Manifest / 状态 / QA）。"""
from __future__ import annotations

from qyunslation.ui.manifest_view import ManifestViewError, summarize_for_ui
from qyunslation.ui.qa import export_gate, qa_items
from qyunslation.ui.state import TASK_STATES, normalize_task_state
from qyunslation.ui.surface import PRODUCTION_SURFACE, describe_surface

__all__ = [
    "PRODUCTION_SURFACE",
    "TASK_STATES",
    "ManifestViewError",
    "describe_surface",
    "export_gate",
    "normalize_task_state",
    "qa_items",
    "summarize_for_ui",
]

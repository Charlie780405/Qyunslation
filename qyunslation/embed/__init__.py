# SPDX-License-Identifier: MPL-2.0
"""PLAN-055：Ollama /api/embed 客户端（与 Hermes embed-mcp 同契约）。"""
from __future__ import annotations

from qyunslation.embed.client import EmbedError, embed_health, embed_texts

__all__ = ["EmbedError", "embed_health", "embed_texts"]

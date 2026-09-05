# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
"""Lightweight Docling config — no docling/torch import at module load."""
from dataclasses import dataclass
from pathlib import Path

from qyunslation.converter.x2md.base import X2MarkdownConverterConfig


@dataclass(kw_only=True)
class ConverterDoclingConfig(X2MarkdownConverterConfig):
    code_ocr: bool = True
    formula_ocr: bool = True
    artifact: Path | str | None = None

    def gethash(self):
        return self.code_ocr, self.formula_ocr

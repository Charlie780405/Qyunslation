# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
from qyunslation.exporter.srt.base import SrtExporter
from qyunslation.ir.document import Document


class Srt2SrtExporter(SrtExporter):
    def export(self, document: Document) -> Document:
        return document.copy()

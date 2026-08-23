# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
from docutranslate.exporter.txt.base import TXTExporter
from docutranslate.ir.document import Document


class Json2JsonExporter(TXTExporter):
    def export(self, document: Document) -> Document:
        return document.copy()

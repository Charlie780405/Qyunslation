# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
from docutranslate.exporter.xlsx.base import XlsxExporter
from docutranslate.ir.document import Document


class Xlsx2XlsxExporter(XlsxExporter):
    def export(self, document: Document) -> Document:
        return document.copy()

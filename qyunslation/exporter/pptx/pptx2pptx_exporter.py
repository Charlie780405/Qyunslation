# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0

from qyunslation.exporter.docx.base import DocxExporter
from qyunslation.ir.document import Document


class PPTX2PPTXExporter(DocxExporter):
    def export(self, document: Document) -> Document:
        return document.copy()

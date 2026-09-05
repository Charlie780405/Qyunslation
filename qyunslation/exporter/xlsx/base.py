# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
from qyunslation.exporter.base import Exporter
from qyunslation.ir.document import Document

#TODO:看情况是否需要为json单独写一个document类型
class XlsxExporter(Exporter[Document]):

    def export(self,document:Document)->Document:
        ...
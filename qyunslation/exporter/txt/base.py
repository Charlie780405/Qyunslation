# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
from qyunslation.exporter.base import Exporter
from qyunslation.ir.document import Document

#TODO:看情况是否需要为TXT单独写一个document类型
class TXTExporter(Exporter[Document]):

    def export(self,document:Document)->Document:
        ...
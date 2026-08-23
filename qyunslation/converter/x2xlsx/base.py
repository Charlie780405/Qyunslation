# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0

from abc import abstractmethod
from dataclasses import dataclass
from typing import Hashable

from docutranslate.converter.base import Converter, ConverterConfig
from docutranslate.ir.document import Document

@dataclass(kw_only=True)
class X2XlsxConverterConfig(ConverterConfig):
    ...
    @abstractmethod
    def gethash(self) ->Hashable:
        ...

class X2XlsxConverter(Converter):
    """
    负责将其它格式的文件转换为xlsx
    """

    @abstractmethod
    def convert(self, document: Document) -> Document:
        ...

    @abstractmethod
    async def convert_async(self, document: Document) -> Document:
        ...

    @abstractmethod
    def support_format(self)->list[str]:
        ...
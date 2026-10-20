# SPDX-License-Identifier: MPL-2.0
"""PLAN-080：Word / PPT 正文段落的"保留原文"（与 PDF 的 babeldoc_policy 同一套规则）。

此前 ``partition_docx_segments`` / ``partition_pptx_segments`` 只对表格单元格有保留策略，正文段落
（作者行、职务、机构、参考文献条目）一律送去翻译。开启 ``QYUNSLATION_OFFICE_PRESERVE=on`` 后，
非表格的段落按与 PDF 相同的规则保留：带学位的人名、职务、机构行、期刊引文与参考文献区。

Word 的段落顺序就是阅读顺序，所以"参考文献"标题之后的状态机在这里是可靠的；每份文档用自己的
``ReferencePreserveGate``，不共享 PDF 路径的全局状态。默认关闭（D3）。
"""
from __future__ import annotations

import os

from .babeldoc_policy import ReferencePreserveGate, paragraph_is_preserved
from .entity_preserve import preserve_reason

MODE_ENV = "QYUNSLATION_OFFICE_PRESERVE"


def office_preserve_enabled() -> bool:
    return (os.environ.get(MODE_ENV) or "off").strip().lower() in {"on", "1", "true", "yes"}


class OfficePreserveGate:
    """一份文档一个实例；按段落的出现顺序判断是否保留。"""

    def __init__(self) -> None:
        self._gate = ReferencePreserveGate()

    def should_preserve(self, text: str | None) -> bool:
        return paragraph_is_preserved(text, gate=self._gate)

    @staticmethod
    def should_preserve_cell(text: str | None) -> bool:
        """表格单元格：只看人名、职务、机构（参会人名单常在表格里），不碰参考文献状态机。"""
        return preserve_reason(text) is not None


def new_office_gate() -> OfficePreserveGate | None:
    """开关关闭时返回 None，调用方据此完全跳过。"""
    return OfficePreserveGate() if office_preserve_enabled() else None

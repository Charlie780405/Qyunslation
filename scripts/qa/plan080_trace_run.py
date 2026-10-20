#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-080b：运行 pdf2zh_next 并记录 BabelDOC 对每个段落的处理（只读追踪，不改引擎文件）。

必须用 pdf2zh-next 自己的 Python 运行，参数原样传给 `pdf2zh_next`：

    QYUNSLATION_PLAN080_TRACE=/path/trace.jsonl PYTHONPATH=<仓库根> \
      ~/.local/share/uv/tools/pdf2zh-next/bin/python scripts/qa/plan080_trace_run.py \
      --config-file ... --lang-in en --lang-out zh --output OUT INPUT.pdf

原理：在启动 CLI 之前导入并包装 `il_translator_llm_only` 的几个方法与谓词。pdf2zh_next 用默认的
fork 方式起翻译子进程，子进程会继承这些包装。不设置 `QYUNSLATION_PLAN080_TRACE` 时本脚本等同于直接运行
`pdf2zh_next`；设置 `QYUNSLATION_FONT_POLICY=unified` 时额外在本进程内安装字体策略（PLAN-080c）。追踪文件含文档节选（每段前 120 字符），不要入库。

事件（每行一个 JSON）：

* seen      process_page 看到的每个段落（页码、段落 ID、长度、节选）
* skip      被谓词排除的段落（reason：cid / numeric / placeholder / target_lang / preserve）
* sent      进入 LLM 批次的段落
* result    译文写回（same=译文与送出文本相同，即 "same as input" 或其他原样返回）
* fallback  LLM 结果被拒后改走普通翻译
报告用 `scripts/qa/plan080_trace_report.py`。
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading

TRACE = os.environ.get("QYUNSLATION_PLAN080_TRACE")
EXCERPT = 120
_LOCK = threading.Lock()


def _excerpt(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:EXCERPT]


def emit(event: str, **fields: object) -> None:
    record = {"event": event, "pid": os.getpid(), **fields}
    line = json.dumps(record, ensure_ascii=False)
    with _LOCK, open(TRACE, "a", encoding="utf-8") as handle:  # type: ignore[arg-type]
        handle.write(line + "\n")


def install() -> None:
    from babeldoc.format.pdf.document_il.midend import il_translator as plain
    from babeldoc.format.pdf.document_il.midend import il_translator_llm_only as llm

    def wrap_predicate(name: str, reason: str, by_text: bool) -> None:
        original = getattr(llm, name)

        def wrapper(arg, *args, **kwargs):
            result = original(arg, *args, **kwargs)
            if result:
                text = arg if by_text else getattr(arg, "unicode", "")
                emit("skip", reason=reason, id=getattr(arg, "debug_id", None), text=_excerpt(text))
            return result

        setattr(llm, name, wrapper)

    wrap_predicate("is_cid_paragraph", "cid", False)
    wrap_predicate("is_pure_numeric_paragraph", "numeric", False)
    wrap_predicate("is_placeholder_only_paragraph", "placeholder", False)
    wrap_predicate("_pdf2zh_skip_already_target_lang", "target_lang", True)
    wrap_predicate("_QY_033H_PRESERVE", "preserve", True)

    if os.environ.get("QYUNSLATION_PLAN080_TRACE_GATE"):
        # 每次调用保留谓词都记录一条（含返回 False 的），并带上调用前的参考文献状态与线程，用来诊断乱序调用
        from qyunslation.structure import babeldoc_policy as policy

        inner = llm._QY_033H_PRESERVE

        def traced_preserve(text):
            before = policy._GATE.in_references
            result = inner(text)
            emit(
                "preserve_call",
                text=_excerpt(text),
                result=bool(result),
                in_refs_before=bool(before),
                in_refs_after=bool(policy._GATE.in_references),
                thread=threading.get_ident(),
                stack=sys._getframe(1).f_code.co_name,
            )
            return result

        llm._QY_033H_PRESERVE = traced_preserve

    cls = llm.ILTranslatorLLMOnly

    original_process_page = cls.process_page

    def process_page(self, page, *args, **kwargs):
        number = getattr(page, "page_number", None)
        for paragraph in list(page.pdf_paragraph):
            if paragraph.debug_id is None or paragraph.unicode is None:
                continue
            emit(
                "seen",
                page=number,
                id=paragraph.debug_id,
                length=len(paragraph.unicode),
                text=_excerpt(paragraph.unicode),
            )
        return original_process_page(self, page, *args, **kwargs)

    cls.process_page = process_page

    original_translate = cls.translate_paragraph

    def translate_paragraph(self, batch_paragraph, *args, **kwargs):
        for paragraph in batch_paragraph.paragraphs:
            emit("sent", id=paragraph.debug_id, text=_excerpt(paragraph.unicode))
        return original_translate(self, batch_paragraph, *args, **kwargs)

    cls.translate_paragraph = translate_paragraph

    il_cls = plain.ILTranslator
    original_post = il_cls.post_translate_paragraph

    def post_translate_paragraph(self, paragraph, tracker, translate_input, translated_text):
        source = getattr(translate_input, "unicode", translate_input)
        same = re.sub(r"\s+", "", str(source or "")) == re.sub(r"\s+", "", str(translated_text or ""))
        emit(
            "result",
            id=paragraph.debug_id,
            same=same,
            source=_excerpt(source),
            output=_excerpt(translated_text),
        )
        return original_post(self, paragraph, tracker, translate_input, translated_text)

    il_cls.post_translate_paragraph = post_translate_paragraph

    original_plain = il_cls.translate_paragraph

    def plain_translate_paragraph(self, paragraph, *args, **kwargs):
        emit("fallback", id=paragraph.debug_id, text=_excerpt(paragraph.unicode))
        return original_plain(self, paragraph, *args, **kwargs)

    il_cls.translate_paragraph = plain_translate_paragraph


def install_font_policy() -> None:
    """PLAN-080c：与生产补丁 apply-pdf2zh-080c-fonts.py 等效，但只在本进程内生效。"""
    from babeldoc.format.pdf.document_il.utils.fontmap import FontMapper
    from qyunslation.structure.font_policy import install as install_policy

    install_policy(FontMapper)


def main() -> int:
    if os.environ.get("QYUNSLATION_FONT_POLICY"):
        install_font_policy()
    if TRACE:
        install()
    from pdf2zh_next.main import cli

    return int(cli() or 0)


if __name__ == "__main__":
    raise SystemExit(main())

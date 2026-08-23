#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-003/004：pdf2zh 吞吐补丁。uv 升级后重跑。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SITE = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
)
GUI = SITE / "pdf2zh_next/gui.py"
OLLAMA = SITE / "pdf2zh_next/translator/translator_impl/ollama.py"
IL = SITE / "babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"

MARKER_UNLOAD = "_cancel_active_translation_on_unload"
TASK_GLOBAL = "_ACTIVE_TRANSLATION_TASK"
MARKER_SKIP = "_pdf2zh_skip_already_target_lang"
MARKER_BATCH = "_PDF2ZH_LLM_BATCH_TOKENS"


def patch_gui(text: str) -> tuple[str, bool]:
    changed = False

    broken = re.compile(
        r"\n        # PLAN-003c: cancel in-flight translation when browser disconnects\n"
        r"        demo\.unload\(\n"
        r"            stop_translate_file,\n"
        r"            inputs=\[state\],\n"
        r"        \)",
        re.MULTILINE,
    )
    if broken.search(text):
        text = broken.sub("", text, count=1)
        changed = True

    if MARKER_UNLOAD not in text:
        anchor = "async def stop_translate_file(state: dict) -> None:"
        helper = (
            f"{TASK_GLOBAL}: asyncio.Task | None = None\n\n\n"
            f"def {MARKER_UNLOAD}() -> None:\n"
            '    """PLAN-003c: cancel active translation when browser refreshes/closes."""\n'
            f"    global {TASK_GLOBAL}\n"
            f"    task = {TASK_GLOBAL}\n"
            "    if task is not None and not task.done():\n"
            '        logger.info("Browser unload: cancelling active translation task")\n'
            "        task.cancel()\n"
            f"    {TASK_GLOBAL} = None\n\n\n"
        )
        if anchor not in text:
            print("ERROR: stop_translate_file anchor not found", file=sys.stderr)
            return text, changed
        text = text.replace(anchor, helper + anchor, 1)
        changed = True

    assign = '            state["current_task"] = task'
    assign_patch = (
        assign + "\n"
        f"            global {TASK_GLOBAL}\n"
        f"            {TASK_GLOBAL} = task"
    )
    if assign in text and assign_patch not in text:
        text = text.replace(assign, assign_patch, 1)
        changed = True

    if (
        '        state["current_task"] = None' in text
        and f"global {TASK_GLOBAL}" not in text.split("stop_translate_file")[1][:800]
    ):
        text = text.replace(
            '    finally:\n        state["current_task"] = None',
            '    finally:\n        state["current_task"] = None\n'
            f"        global {TASK_GLOBAL}\n"
            f"        {TASK_GLOBAL} = None",
            1,
        )
        changed = True

    cancel_anchor = """        # Cancel button click handler
        cancel_btn.click(
            stop_translate_file,
            inputs=[state],
        )"""
    unload_block = f"""

        # PLAN-003c: cancel in-flight translation when browser disconnects
        demo.unload({MARKER_UNLOAD})"""
    if f"demo.unload({MARKER_UNLOAD})" not in text:
        if cancel_anchor in text:
            text = text.replace(cancel_anchor, cancel_anchor + unload_block, 1)
            changed = True

    notice_block = (
        "        gr.Markdown(\n"
        '            "> **PLAN-003a: do not refresh while translating** — '
        "进度停在 Term Extraction 通常是在跑术语抽取（已默认关闭）；"
        '翻译中刷新会断开连接并取消任务。"\n'
        '            , elem_classes=["secondary-text"]\n'
        "        )\n"
    )
    if notice_block in text:
        text = text.replace(notice_block, "", 1)
        changed = True

    cache_anchor = '        token_info = f"\\n\\n**Total Token Usage:**'
    cache_log = """        if all_token_usage["prompt"]:
            logger.info(
                "PLAN-004b cache: hit_prompt=%s prompt=%s ratio=%.3f",
                all_token_usage["cache_hit_prompt"],
                all_token_usage["prompt"],
                all_token_usage["cache_hit_prompt"] / max(all_token_usage["prompt"], 1),
            )

        token_info = f"\\n\\n**Total Token Usage:**"""
    if "PLAN-004b cache" not in text and cache_anchor in text:
        text = text.replace(cache_anchor, cache_log, 1)
        changed = True

    return text, changed


def patch_ollama(text: str) -> tuple[str, bool]:
    changed = False
    old = """        if (max_token := len(text) * 5) > self.options["num_predict"]:
            self.options["num_predict"] = max_token"""
    new = """        if (max_token := min(len(text) * 5, 1024)) > self.options["num_predict"]:
            self.options["num_predict"] = max_token"""
    if old in text:
        text = text.replace(old, new)
        changed = True
    elif "min(len(text) * 5, 1024)" not in text:
        print("WARN: ollama num_predict anchor not found", file=sys.stderr)
    return text, changed


def patch_il(text: str) -> tuple[str, bool]:
    changed = False

    helper_block = f'''
import os

# PLAN-004b/c throughput knobs (apply-pdf2zh-throughput.py)
_PDF2ZH_SKIP_ALREADY_TARGET_COUNT = 0
_PDF2ZH_LLM_BATCH_TOKENS = int(os.environ.get("PDF2ZH_LLM_BATCH_TOKENS", "400"))
_PDF2ZH_LLM_BATCH_PARAS = int(os.environ.get("PDF2ZH_LLM_BATCH_PARAS", "8"))


def _pdf2zh_han_ratio(text: str) -> float:
    if not text:
        return 0.0
    han = sum(1 for c in text if "\\u4e00" <= c <= "\\u9fff")
    return han / len(text)


def _pdf2zh_latin_ratio(text: str) -> float:
    if not text:
        return 0.0
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return latin / len(text)


def {MARKER_SKIP}(text: str, lang_in: str, lang_out: str) -> bool:
    global _PDF2ZH_SKIP_ALREADY_TARGET_COUNT
    lang_in = (lang_in or "").lower()
    lang_out = (lang_out or "").lower()
    han = _pdf2zh_han_ratio(text)
    latin = _pdf2zh_latin_ratio(text)
    skip = False
    if lang_out.startswith("zh"):
        skip = han >= 0.8 and latin <= 0.15
    elif lang_in.startswith("zh") and lang_out.startswith("en"):
        skip = han < 0.8
    if skip:
        _PDF2ZH_SKIP_ALREADY_TARGET_COUNT += 1
    return skip

'''

    if MARKER_SKIP not in text:
        anchor = "logger = logging.getLogger(__name__)"
        if anchor not in text:
            print("ERROR: il_translator logger anchor not found", file=sys.stderr)
            return text, changed
        text = text.replace(anchor, anchor + helper_block, 1)
        changed = True

    skip_check = f"""            if {MARKER_SKIP}(
                paragraph.unicode,
                self.translation_config.lang_in,
                self.translation_config.lang_out,
            ):
                if pbar:
                    pbar.advance(1)
                translated_ids.add(id(paragraph))
                continue

"""
    placeholder_anchor = """            if is_placeholder_only_paragraph(paragraph):
                if pbar:
                    pbar.advance(1)
                continue

            # self.translate_paragraph"""
    if MARKER_SKIP not in text.split("process_page")[1][:2500]:
        if placeholder_anchor in text:
            text = text.replace(
                placeholder_anchor,
                placeholder_anchor.replace(
                    "continue\n\n            # self.translate_paragraph",
                    "continue\n\n" + skip_check.rstrip() + "\n            # self.translate_paragraph",
                ),
                1,
            )
            changed = True

    if "if total_token_count > 200 or len(paragraphs) > 5:" in text:
        text = text.replace(
            "if total_token_count > 200 or len(paragraphs) > 5:",
            "if total_token_count > _PDF2ZH_LLM_BATCH_TOKENS or len(paragraphs) > _PDF2ZH_LLM_BATCH_PARAS:",
        )
        changed = True

    summary_anchor = """        path = self.translation_config.get_working_file_path("translate_tracking.json")"""
    summary_log = f"""        if _PDF2ZH_SKIP_ALREADY_TARGET_COUNT:
            logger.info(
                "skip already-target-lang count=%s",
                _PDF2ZH_SKIP_ALREADY_TARGET_COUNT,
            )

        path = self.translation_config.get_working_file_path("translate_tracking.json")"""
    if "skip already-target-lang count" not in text and summary_anchor in text:
        text = text.replace(summary_anchor, summary_log, 1)
        changed = True

    return text, changed


def apply_file(path: Path, patcher) -> bool:
    if not path.is_file():
        print(f"ERROR: not found: {path}", file=sys.stderr)
        return False
    original = path.read_text(encoding="utf-8")
    updated, changed = patcher(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        print("patched:", path)
    else:
        print("already patched:", path)
    return True


def main() -> int:
    ok = True
    ok = apply_file(GUI, patch_gui) and ok
    ok = apply_file(OLLAMA, patch_ollama) and ok
    ok = apply_file(IL, patch_il) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

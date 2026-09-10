"""PLAN-041a：中英混排段落不得被目标语种门误跳过。"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_patcher():
    path = Path(__file__).resolve().parents[2] / "scripts/apply-pdf2zh-throughput.py"
    spec = importlib.util.spec_from_file_location("apply_pdf2zh_throughput", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_patcher_upgrades_existing_ratio_based_chinese_to_english_skip():
    patcher = _load_patcher()
    source = '''
def _pdf2zh_skip_already_target_lang(text: str, lang_in: str, lang_out: str) -> bool:
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

    patched, changed = patcher.patch_il(source)

    assert changed is True
    assert 'skip = han < 0.8' not in patched
    assert 'skip = han == 0.0' in patched
    assert '_PDF2ZH_SKIP_REASONS[reason]' in patched


def test_new_helper_translates_any_paragraph_that_still_contains_han():
    patcher = _load_patcher()
    source = '''
import logging
logger = logging.getLogger(__name__)

def process_page(self):
            if is_placeholder_only_paragraph(paragraph):
                if pbar:
                    pbar.advance(1)
                continue

            # self.translate_paragraph
'''

    patched, changed = patcher.patch_il(source)

    assert changed is True
    assert 'skip = han == 0.0' in patched
    assert 'reason = "source-script-present"' in patched
    assert 'reason = "already-target"' in patched


def test_language_helper_patch_is_idempotent():
    patcher = _load_patcher()
    source = '''
import logging
logger = logging.getLogger(__name__)

def process_page(self):
            if is_placeholder_only_paragraph(paragraph):
                if pbar:
                    pbar.advance(1)
                continue

            # self.translate_paragraph
'''
    patched, changed = patcher.patch_il(source)
    again, second_changed = patcher.patch_il(patched)

    assert changed is True
    assert second_changed is False
    assert again == patched

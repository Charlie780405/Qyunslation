# SPDX-License-Identifier: MPL-2.0
"""enhanced_translate 单元测试（mock 网络，测术语表注入 + 嵌字调度逻辑）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import enhanced_translate


def test_enhanced_translate_injects_glossary(monkeypatch):
    """验证 custom_glossary 被转成 custom_prompt 注入翻译。"""
    captured = {}

    def fake_submit(file_bytes, filename, to_lang, custom_prompt=None):
        captured["custom_prompt"] = custom_prompt
        return "task123"

    def fake_poll(task_id, file_type="docx", max_wait=600):
        captured["file_type"] = file_type
        return b"fake_docx_result"

    monkeypatch.setattr(enhanced_translate, "_submit_translate", fake_submit)
    monkeypatch.setattr(enhanced_translate, "_poll_download", fake_poll)

    result, meta = enhanced_translate.enhanced_translate(
        b"fake", "test.txt", to_lang="中文",
        use_glossary=False, translate_images=False,
        custom_glossary={"OX40-OX40L pathway": "OX40/OX40L信号轴"},
    )
    assert "必须使用指定译法" in captured["custom_prompt"]
    assert "OX40-OX40L pathway => OX40/OX40L信号轴" in captured["custom_prompt"]
    assert meta["glossary_terms"] == 1
    assert result == b"fake_docx_result"


def test_enhanced_translate_skip_glossary_when_disabled(monkeypatch):
    captured = {}

    def fake_submit(file_bytes, filename, to_lang, custom_prompt=None):
        captured["custom_prompt"] = custom_prompt
        return "task123"

    def fake_poll(task_id, file_type="docx", max_wait=600):
        return b"result"

    monkeypatch.setattr(enhanced_translate, "_submit_translate", fake_submit)
    monkeypatch.setattr(enhanced_translate, "_poll_download", fake_poll)

    enhanced_translate.enhanced_translate(b"fake", "test.txt", use_glossary=False, translate_images=False)
    assert captured["custom_prompt"] is None  # 不注入术语表

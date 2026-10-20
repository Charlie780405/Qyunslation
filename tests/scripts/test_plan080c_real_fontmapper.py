# SPDX-License-Identifier: MPL-2.0
"""PLAN-080c：用 pdf2zh 自己的 Python 环境里真实的 BabelDOC FontMapper 验证字体策略。

替身测试（tests/structure/test_plan080_font_policy.py）只能证明选择逻辑；这里证明它确实挂得上真实的
``FontMapper.map``，并且关闭时行为与原来一致。该环境不在仓库里（uv tool），不存在时整组跳过。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PY = Path(os.environ.get("QYUNSLATION_PDF2ZH_PY", Path.home() / ".local/share/uv/tools/pdf2zh-next/bin/python"))

pytestmark = pytest.mark.skipif(not TOOL_PY.is_file(), reason="pdf2zh-next tool environment not installed")

SCRIPT = r"""
import json, os, sys
sys.path.insert(0, os.environ["QY_REPO_ROOT"])
from types import SimpleNamespace
from babeldoc.format.pdf.document_il.utils.fontmap import FontMapper
from babeldoc.format.pdf.document_il.il_version_1 import PdfFont
from qyunslation.structure.font_policy import install

install(FontMapper)
mapper = FontMapper(SimpleNamespace(lang_out=os.environ.get("QY_LANG_OUT", "zh"), primary_font_family=None))
def font(name, bold=False, italic=False):
    return PdfFont(name=name, font_id="F1", xref_id=1, encoding_length=1, bold=bold, italic=italic,
                   monospace=False, serif=False, ascent=0, descent=0, pdf_font_char_bounding_box=[])
result = {}
for label, f in (("italic", font("Arial-ItalicMT", italic=True)), ("regular", font("ArialMT")), ("bold", font("Arial-BoldMT", bold=True))):
    for ch in ("中", "B"):
        picked = mapper.map(f, ch)
        result[f"{label}:{ch}"] = getattr(picked, "font_id", None)
print(json.dumps(result))
"""


def _map(policy: str | None, lang_out: str = "zh") -> dict[str, str]:
    env = {**os.environ, "QY_REPO_ROOT": str(ROOT), "QY_LANG_OUT": lang_out}
    env.pop("QYUNSLATION_FONT_POLICY", None)
    if policy:
        env["QYUNSLATION_FONT_POLICY"] = policy
    done = subprocess.run([str(TOOL_PY), "-I", "-c", SCRIPT], env=env, capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stderr[-800:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_unified_policy_picks_one_family_on_the_real_font_mapper():
    mapped = _map("unified")
    assert mapped["italic:中"] == mapped["regular:中"] == "SourceHanSerifCN-Regular.ttf"
    assert mapped["italic:B"] == mapped["regular:B"] == "SourceHanSerifCN-Regular.ttf"
    assert mapped["bold:中"] == mapped["bold:B"] == "SourceHanSerifCN-Bold.ttf"


def test_policy_off_keeps_the_original_mixed_mapping():
    mapped = _map(None)
    # 原行为：斜体汉字走霞鹜文楷，拉丁走 Noto 系列；这正是需要统一的现象
    assert mapped["italic:中"] != "SourceHanSerifCN-Regular.ttf"
    assert mapped["regular:B"].startswith("Noto")  # 拉丁字符落到 Noto 系列，与思源汉字不同族


def test_policy_does_not_interfere_when_the_target_language_is_english():
    """中译英：字体表里没有思源，策略回落到原行为，输出与关闭时完全一致。"""
    assert _map("unified", lang_out="en") == _map(None, lang_out="en")

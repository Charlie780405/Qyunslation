"""PLAN-030 金样寻址。

PLAN-030h H1 起，主门断言一律走仓内合成等价夹具（见
``tests/fixtures/structure/generate_synthetic.py`` 与 session fixture
``generated_structure_fixtures``）。

这里的仓外样本只作**加强回归**：默认根 ``/home/dev/pdf2zh/pdf2zh_files`` 是
pdf2zh 的运行时会话目录，里面是 UUID 命名的用户上传件，会被会话回收，也不随
仓库迁移，因此不得作为任何断言的锚。缺失时相关加强项 skip，主门不受影响。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_SAMPLE_ROOT = Path("/home/dev/pdf2zh/pdf2zh_files")

SLIDE_DIR = (
    "57114032-8727-41f9-b826-b5ff40fcf733/QX027N QnA-2026.08.19-临床.pdf"
)
PIND_DIR = "5fa54bcf-4843-4e97-8cd0-85c797fa9b5d"
PIND_PDF = f"{PIND_DIR}/FDA responses on PIND.pdf"
PIND_OCR = f"{PIND_DIR}/FDA responses on PIND.hpd-ocr.pdf"

# 合成等价件与仓外金样共有的形态契约，两边断言同一组数字
SCANNED_PAGE_COUNT = 20
SLIDE_TRANSLATABLE_REGIONS = 12

# 双轨参数化：合成件为主门，仓外件缺失时 skip（fixture 见 conftest.py）
both_scanned = pytest.mark.parametrize(
    "scanned_pdf", ["synthetic", "external"], indirect=True
)
both_ocr = pytest.mark.parametrize("ocr_pdf", ["synthetic", "external"], indirect=True)
both_slides = pytest.mark.parametrize(
    "slide_pdf", ["synthetic", "external"], indirect=True
)


def sample_root() -> Path:
    override = os.environ.get("QYUNSLATION_SAMPLE_ROOT", "").strip()
    if override:
        return Path(override)
    return _DEFAULT_SAMPLE_ROOT


def slide_sample() -> Path:
    return sample_root() / SLIDE_DIR


def pind_sample() -> Path:
    return sample_root() / PIND_PDF


def pind_ocr_sample() -> Path:
    return sample_root() / PIND_OCR


def missing_sample_report() -> list[str]:
    """Human-readable list of configured samples that are absent on disk."""
    missing: list[str] = []
    for label, path in (
        ("slide", slide_sample()),
        ("pind", pind_sample()),
        ("pind_ocr", pind_ocr_sample()),
    ):
        if not path.is_file():
            missing.append(f"{label}:{path}")
    return missing

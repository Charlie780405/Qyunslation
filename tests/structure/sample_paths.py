"""Resolve optional out-of-repo PLAN-030 gold samples for structure tests."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_SAMPLE_ROOT = Path("/home/dev/pdf2zh/pdf2zh_files")

SLIDE_DIR = (
    "57114032-8727-41f9-b826-b5ff40fcf733/QX027N QnA-2026.08.19-临床.pdf"
)
PIND_DIR = "5fa54bcf-4843-4e97-8cd0-85c797fa9b5d"
PIND_PDF = f"{PIND_DIR}/FDA responses on PIND.pdf"
PIND_OCR = f"{PIND_DIR}/FDA responses on PIND.hpd-ocr.pdf"


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

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.structure.sample_paths import (
    pind_ocr_sample,
    pind_sample,
    slide_sample,
)


@pytest.fixture(scope="session")
def generated_structure_fixtures(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = Path(__file__).resolve().parents[2]
    generator_path = root / "tests" / "fixtures" / "structure" / "generate_synthetic.py"
    spec = importlib.util.spec_from_file_location("plan030_session_fixtures", generator_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path_factory.mktemp("plan030-structure")
    module.generate_all(output)
    return output


def _dual_source(
    request: pytest.FixtureRequest,
    generated_root: Path,
    *,
    synthetic_name: str,
    external: Path,
    label: str,
) -> Path:
    """PLAN-030h H1：合成等价件是主门来源，仓外金样存在时作加强回归。

    仓外样本躺在 pdf2zh 的运行时会话目录里，会被回收，不能作为断言的锚。
    """
    if request.param == "synthetic":
        return generated_root / synthetic_name
    if not external.is_file():
        pytest.skip(f"仓外{label}金样缺失，加强回归跳过：{external}")
    return external


@pytest.fixture
def scanned_pdf(request, generated_structure_fixtures) -> Path:
    return _dual_source(
        request,
        generated_structure_fixtures,
        synthetic_name="scanned-equivalent.pdf",
        external=pind_sample(),
        label="扫描",
    )


@pytest.fixture
def ocr_pdf(request, generated_structure_fixtures) -> Path:
    return _dual_source(
        request,
        generated_structure_fixtures,
        synthetic_name="scanned-equivalent.hpd-ocr.pdf",
        external=pind_ocr_sample(),
        label=" OCR ",
    )


@pytest.fixture
def slide_pdf(request, generated_structure_fixtures) -> Path:
    return _dual_source(
        request,
        generated_structure_fixtures,
        synthetic_name="slide-equivalent.pdf",
        external=slide_sample(),
        label="幻灯",
    )

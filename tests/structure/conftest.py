from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


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

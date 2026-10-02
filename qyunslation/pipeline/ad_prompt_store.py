"""PLAN-076i: freeze compiled AD prompts at run creation and verify at launch."""
from __future__ import annotations

import json
import os
from pathlib import Path

PROMPT_SUBDIR = "prompt"
COMPILED_FILENAME = "compiled-system.txt"
MANIFEST_FILENAME = "manifest.json"


def prompt_dir(run_dir: Path) -> Path:
    return run_dir / PROMPT_SUBDIR


def write_frozen_prompt(run_dir: Path, *, text: str, snapshot: dict) -> Path:
    directory = prompt_dir(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    compiled = directory / COMPILED_FILENAME
    compiled.write_text(text, encoding="utf-8")
    os.chmod(compiled, 0o600)
    manifest = {
        "digest": snapshot.get("digest"),
        "snapshot": snapshot,
    }
    (directory / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return compiled


def load_frozen_prompt(run_dir: Path) -> tuple[str, dict] | None:
    compiled = prompt_dir(run_dir) / COMPILED_FILENAME
    manifest_path = prompt_dir(run_dir) / MANIFEST_FILENAME
    if not compiled.is_file() or not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return compiled.read_text(encoding="utf-8"), manifest


def verify_frozen_digest(run_dir: Path, expected_digest: str) -> bool:
    loaded = load_frozen_prompt(run_dir)
    if loaded is None:
        return False
    _, manifest = loaded
    actual = str(manifest.get("digest") or "").strip()
    expected = str(expected_digest or "").strip()
    return bool(actual and expected and actual == expected)

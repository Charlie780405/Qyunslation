# SPDX-License-Identifier: MPL-2.0
"""PLAN-074 BabelDOC paragraph postprocessing and front-matter evidence trace."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from qyunslation.structure.frontmatter import AFFILIATION, classify_frontmatter_text
from qyunslation.structure.text_sanitize import sanitize_translated_text

OVERRIDES_FILE = ".qyunslation-review-overrides.json"
TRACE_FILE = ".qyunslation-frontmatter.jsonl"
_TRACE_LOCK = threading.Lock()


def load_affiliation_trace(path: Path) -> list[dict[str, object]]:
    """Read deterministic affiliation evidence, tolerating partial retry writes."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for line in lines:
        try:
            raw = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(raw, dict) or raw.get("role") != AFFILIATION:
            continue
        source = raw.get("source_text")
        machine = raw.get("machine_text")
        if not isinstance(source, str) or not source.strip() or not isinstance(machine, str):
            continue
        identity = (source, machine)
        if identity in seen:
            continue
        seen.add(identity)
        records.append(raw)
    return records


def postprocess_translation(
    source_text: str | None,
    translated_text: str | None,
    *,
    workdir: Path | None = None,
) -> str:
    """Apply exact reviewed paragraphs, sanitize output, and trace affiliations."""
    source = source_text or ""
    root = workdir or Path.cwd()
    output = translated_text or ""
    override_path = root / OVERRIDES_FILE
    try:
        overrides = json.loads(override_path.read_text(encoding="utf-8"))
        if isinstance(overrides, dict) and source in overrides:
            output = str(overrides[source])
    except (OSError, ValueError, TypeError):
        pass
    output, _codes = sanitize_translated_text(output)
    classification = classify_frontmatter_text(source)
    if classification.role == AFFILIATION:
        record = {
            "source_text": source,
            "machine_text": output,
            "role": AFFILIATION,
            "confidence": classification.confidence,
        }
        try:
            with _TRACE_LOCK, (root / TRACE_FILE).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return output

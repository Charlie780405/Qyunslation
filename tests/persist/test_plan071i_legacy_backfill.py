# SPDX-License-Identifier: MPL-2.0
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "alembic/versions/071i0001_legacy_unverified_backfill.py"


def test_migration_marks_succeeded_as_legacy_unverified():
    text = MIG.read_text(encoding="utf-8")
    assert "legacy_unverified" in text
    assert "status = 'succeeded'" in text
    assert "kind = 'legacy'" in text

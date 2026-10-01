# SPDX-License-Identifier: MPL-2.0
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_plan073_migration_chain():
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    rev = script.get_revision("073a0001")
    assert rev.down_revision == "072a0001"
    upgrade = rev.module.upgrade
    assert upgrade is not None

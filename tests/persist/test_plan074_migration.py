# SPDX-License-Identifier: MPL-2.0
from alembic.config import Config
from alembic.script import ScriptDirectory

from qyunslation.persist.models import DocumentTermCandidate, ReviewSegment


def test_plan074_migration_chain_and_review_metadata_contract():
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    rev = script.get_revision("074a0001")

    assert rev.down_revision == "073a0001"
    assert "translation_run_id" in ReviewSegment.__table__.columns
    assert "generation" in ReviewSegment.__table__.columns
    assert "page_no" in ReviewSegment.__table__.columns
    assert "bbox" in ReviewSegment.__table__.columns
    assert "extraction_metadata" in DocumentTermCandidate.__table__.columns

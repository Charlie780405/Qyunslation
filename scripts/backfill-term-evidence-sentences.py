#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Give an existing run's term candidates complete-sentence evidence (no model calls).

Candidates stored before this change keep one PDF *line* per occurrence; this re-derives the sentence
from the run's source text. Dry run by default (nothing is written); pass --apply to save.

    QYUNSLATION_DATABASE_URL=... python scripts/backfill-term-evidence-sentences.py RUN_ID [--apply]
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--apply", action="store_true", help="save the changes (default: dry run)")
    args = parser.parse_args()

    from qyunslation.api import v1
    from qyunslation.persist import db as persist_db
    from qyunslation.persist.models import TranslationRunRecord
    from qyunslation.workbench.term_extract import refresh_occurrence_contexts

    v1.ensure_engine_ready()
    if persist_db.SessionLocal is None:
        print("database is not configured (QYUNSLATION_DATABASE_URL)", file=sys.stderr)
        return 2
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, args.run_id)
        if run is None:
            print(f"run {args.run_id} not found", file=sys.stderr)
            return 1
        runner_state = None
        if run.external_task_id:
            try:
                from qyunslation.workbench.runner import get_pdf2zh_task_state

                runner_state = get_pdf2zh_task_state(run.external_task_id)
            except Exception:
                runner_state = None
        if runner_state is None:
            runner_state = v1._persisted_executor_state(run)
        _findings, _term_snapshot, facts = v1._inspect_run_outputs(session, run, runner_state)
        if not facts or "source" not in facts:
            print("source text is not available for this run; nothing changed", file=sys.stderr)
            return 1
        stats = refresh_occurrence_contexts(session, run=run, source_text=facts["source"].text)
        print({"run": run.id, **stats, "mode": "apply" if args.apply else "dry-run"})
        if args.apply:
            session.commit()
        else:
            session.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

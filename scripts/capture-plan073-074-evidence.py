#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Capture PLAN-073/074 browser evidence PNGs via local dev evidence server."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "plan073-074"
VAR = ROOT / "var" / "plan073-074-evidence"


def _ensure_fake_cli(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('--output') + 1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "src = pathlib.Path(args[-1])\n"
        "for name in (src.stem + '_dual.pdf', src.stem + '.pdf'):\n"
        "    (out / name).write_bytes(b'%PDF-1.7 evidence')\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _configure_env() -> None:
    for name in ("preflights", "artifacts", "runs", "pipeline", "db"):
        (VAR / name).mkdir(parents=True, exist_ok=True)
    cli = VAR / "fake-pdf2zh"
    _ensure_fake_cli(cli)
    os.environ["QYUNSLATION_ENV"] = "development"
    os.environ["QYUNSLATION_DEV_AUTH_BYPASS"] = "1"
    os.environ["QYUNSLATION_DATABASE_URL"] = f"sqlite+pysqlite:///{VAR / 'db' / 'app.db'}"
    os.environ["QYUNSLATION_PREFLIGHT_ROOT"] = str(VAR / "preflights")
    os.environ["QYUNSLATION_ARTIFACT_ROOT"] = str(VAR / "artifacts")
    os.environ["QYUNSLATION_RUNNER_ROOT"] = str(VAR / "runs")
    os.environ["QYUNSLATION_PIPELINE_ROOT"] = str(VAR / "pipeline")
    os.environ["QYUNSLATION_PIPELINE"] = "v2"
    os.environ["QYUNSLATION_PDF2ZH_CLI"] = str(cli)
    os.environ["QYUNSLATION_BROWSER_HOST"] = "127.0.0.1"
    os.environ["QYUNSLATION_BROWSER_PORT"] = "8788"


def _seed() -> dict[str, str]:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from qyunslation.api.v1 import router as api_v1_router
    from qyunslation.persist import db as persist_db
    from qyunslation.persist.db import init_engine, reset_engine
    from qyunslation.persist.models import Base, PreflightRecord, TranslationRunRecord
    from qyunslation.pipeline.event_store import persist_buffer
    from qyunslation.pipeline.events import StageEventBuffer
    from qyunslation.workbench.term_extract import (
        extract_candidates_from_text,
        sync_affiliation_segments_from_text,
    )

    db_file = VAR / "db" / "app.db"
    if db_file.exists():
        db_file.unlink()

    reset_engine()
    engine = init_engine(os.environ["QYUNSLATION_DATABASE_URL"])
    Base.metadata.create_all(engine)

    app = FastAPI()
    app.include_router(api_v1_router)
    client = TestClient(app)
    headers = {
        "X-Dev-User": "evidence-reviewer",
        "X-Dev-Tenant": "pilot",
        "X-Dev-Role": "system_admin,reviewer,workbench_v2,admin",
    }

    def make_run(key: str, *, filename: str, pdf_bytes: bytes) -> str:
        preflight = client.post(
            "/api/v1/preflights",
            headers=headers,
            files={"file": (filename, pdf_bytes, "application/pdf")},
        ).json()
        created = client.post(
            "/api/v1/translation-runs",
            headers={**headers, "Idempotency-Key": key},
            json={"preflight_id": preflight["id"]},
        )
        assert created.status_code == 201, created.text
        return created.json()["id"]

    workbench_id = make_run("evidence-workbench", filename="dupilumab-poster.pdf", pdf_bytes=b"%PDF-1.7 workbench")
    term_id = make_run("evidence-term", filename="term-review.pdf", pdf_bytes=b"%PDF-1.7 term")
    affiliation_id = make_run("evidence-affiliation", filename="affiliation-review.pdf", pdf_bytes=b"%PDF-1.7 affiliation")

    assert persist_db.SessionLocal is not None
    with persist_db.SessionLocal() as session:
        workbench = session.get(TranslationRunRecord, workbench_id)
        assert workbench is not None
        workbench.status = "rendering"
        workbench.stage = "qa"
        workbench.quality_state = "qa_blocked"
        workbench.progress = 92.0
        workbench.qa_summary = {"blocker": 2, "warning": 1, "info": 0}
        workbench.display_name = "Dupilumab Poster（QA 拦截样本）"

        buffer = StageEventBuffer()
        for stage, state, message in (
            ("validation", "completed", "预检通过"),
            ("structure", "completed", "结构分析完成"),
            ("text", "completed", "正文翻译完成"),
            ("layout", "completed", "版式渲染完成"),
            ("qa", "blocked", "发现 2 项 QA 阻断"),
        ):
            buffer.emit(stage, state, message=message)
        persist_buffer(session, run_id=workbench_id, generation=workbench.generation, buffer=buffer)

        term_run = session.get(TranslationRunRecord, term_id)
        term_preflight = session.get(PreflightRecord, term_run.preflight_id)
        term_run.quality_state = "review_ready"
        term_run.status = "review_ready"
        term_run.stage = "review"
        term_run.qa_summary = {"blocker": 0, "warning": 0, "info": 0}
        term_run.display_name = "术语审校样本"
        extract_candidates_from_text(
            session,
            run=term_run,
            preflight=term_preflight,
            source_text="Dupilumab improved outcomes in atopic dermatitis and vitiligo.",
            translated_text="度普利尤单抗改善了特应性皮炎和白癜风的结局。",
        )

        aff_run = session.get(TranslationRunRecord, affiliation_id)
        aff_preflight = session.get(PreflightRecord, aff_run.preflight_id)
        aff_run.quality_state = "review_ready"
        aff_run.status = "review_ready"
        aff_run.stage = "review"
        aff_run.display_name = "单位译名样本"
        source = "1 Department of Dermatology, New York Medical College"
        machine = "1 纽约医学院皮肤病学系"
        trace_path = VAR / "pipeline" / f"{affiliation_id}-trace.jsonl"
        trace_path.write_text(
            json.dumps(
                {"source_text": source, "machine_text": machine, "role": "affiliation"},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        sync_affiliation_segments_from_text(
            session,
            run=aff_run,
            preflight=aff_preflight,
            source_text=source,
            translated_text="此处是无法可靠对齐的成稿文本",
            trace_path=trace_path,
        )
        session.commit()

    reset_engine()
    return {
        "workbench": workbench_id,
        "term": term_id,
        "affiliation": affiliation_id,
    }


def _chromium_bin() -> Path:
    local = Path.home() / ".local" / "bin" / "chromium"
    if local.is_file():
        return local
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / ".cache/ms-playwright"))
    matches = sorted(root.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    if not matches:
        raise SystemExit("headless chromium not found; run scripts/install-headless-chromium.sh")
    return matches[-1]


def _screenshot(url: str, dest: Path, *, width: int = 1440, height: int = 960) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(_chromium_bin()),
        "--headless",
        "--no-sandbox",
        "--disable-gpu",
        f"--window-size={width},{height}",
        f"--screenshot={dest}",
        "--hide-scrollbars",
        "--virtual-time-budget=8000",
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _wait_ready(base: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/v1/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.4)
    raise SystemExit(f"evidence server not ready: {base}")


def main() -> int:
    _configure_env()
    ids = _seed()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    server = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "dev_plan071_browser_server.py")],
        cwd=str(ROOT),
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://{os.environ['QYUNSLATION_BROWSER_HOST']}:{os.environ['QYUNSLATION_BROWSER_PORT']}"
    try:
        _wait_ready(base)
        shots = [
            (f"{base}/next/workbench", EVIDENCE_DIR / "workbench-timeline-dedupe.png", 1440, 960),
            (f"{base}/next/workbench", EVIDENCE_DIR / "workbench-qa-blocked-status.png", 1440, 960),
            (f"{base}/next/workbench/{ids['term']}", EVIDENCE_DIR / "run-detail-term-panel.png", 1440, 2200),
            (
                f"{base}/next/workbench/{ids['affiliation']}",
                EVIDENCE_DIR / "run-detail-affiliation-panel.png",
                1440,
                2200,
            ),
        ]
        for url, path, width, height in shots:
            _screenshot(url, path, width=width, height=height)
            print(f"OK: {path.name} ({path.stat().st_size} bytes)")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        if server.stderr:
            err = server.stderr.read()
            if err and server.returncode not in (0, -15):
                print(err, file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

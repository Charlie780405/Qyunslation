#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Minimal server for PLAN-071 browser evidence (Next SPA + API v1)."""
from __future__ import annotations

import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ensure_fake_cli(path: Path) -> None:
    """Fake pdf2zh executor: stamps a draft banner on a real PDF (evidence only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys, time\n"
        "import fitz\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('--output') + 1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "src = pathlib.Path(args[-1])\n"
        "print('Progress: 0.3 translating', flush=True); time.sleep(0.4)\n"
        "doc = fitz.open(str(src))\n"
        "for page in doc:\n"
        "    page.insert_text((40, 40), '译文预览（证据样本，非真实翻译）· QYUNSLATION REVIEW DRAFT',\n"
        "                     fontname='china-s', fontsize=11, color=(0.1, 0.3, 0.6))\n"
        "for name in (src.stem + '_dual.pdf', src.stem + '.pdf'):\n"
        "    doc.save(str(out / name))\n"
        "print('Progress: 1.0, export', flush=True)\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def main() -> None:
    var = ROOT / "var" / "plan071-browser"
    for name in ("preflights", "artifacts", "runs", "pipeline", "db"):
        (var / name).mkdir(parents=True, exist_ok=True)
    cli = var / "fake-pdf2zh"
    _ensure_fake_cli(cli)

    os.environ.setdefault("QYUNSLATION_ENV", "development")
    os.environ.setdefault("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    os.environ.setdefault("QYUNSLATION_DATABASE_URL", f"sqlite+pysqlite:///{var / 'db' / 'app.db'}")
    os.environ.setdefault("QYUNSLATION_PREFLIGHT_ROOT", str(var / "preflights"))
    os.environ.setdefault("QYUNSLATION_ARTIFACT_ROOT", str(var / "artifacts"))
    os.environ.setdefault("QYUNSLATION_RUNNER_ROOT", str(var / "runs"))
    os.environ.setdefault("QYUNSLATION_PIPELINE_ROOT", str(var / "pipeline"))
    os.environ.setdefault("QYUNSLATION_PIPELINE", "v2")
    os.environ.setdefault("QYUNSLATION_PDF2ZH_CLI", str(cli))

    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.middleware.cors import CORSMiddleware

    from qyunslation.api.v1 import router as api_v1_router
    from qyunslation.persist.db import init_engine
    from qyunslation.persist.models import Base

    engine = init_engine(os.environ["QYUNSLATION_DATABASE_URL"])
    Base.metadata.create_all(engine)

    class EvidenceAuthHeaders(BaseHTTPMiddleware):
        """Inject reviewer/admin roles for local evidence browsing."""

        async def dispatch(self, request: Request, call_next):
            headers = MutableHeaders(scope=request.scope)
            headers.setdefault("X-Dev-User", "evidence-reviewer")
            headers.setdefault("X-Dev-Tenant", "pilot")
            # system_admin first so _identity_role maps to admin (can_manage_policy).
            headers.setdefault(
                "X-Dev-Role", "system_admin,reviewer,workbench_v2,admin"
            )
            return await call_next(request)

    from starlette.datastructures import MutableHeaders

    app = FastAPI(title="PLAN-071 browser evidence")
    app.add_middleware(EvidenceAuthHeaders)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_v1_router)

    next_dir = ROOT / "qyunslation" / "static" / "app"
    assets = next_dir / "assets"
    if assets.is_dir():
        app.mount("/app-assets/assets", StaticFiles(directory=assets), name="next-assets")
    # also mount other static files under /app-assets
    app.mount("/app-assets", StaticFiles(directory=next_dir), name="next-root")

    @app.get("/next", response_class=HTMLResponse)
    @app.get("/next/{path:path}", response_class=HTMLResponse)
    def next_spa(path: str = ""):
        return FileResponse(next_dir / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/auth/login")
    def auth_login(format: str = "html", return_to: str = "/next/workbench"):
        # Dev evidence: pretend OIDC is unavailable but allow /me via bypass.
        if format == "json":
            return {
                "message": "dev bypass active — open /next/workbench directly",
                "location": return_to if return_to.startswith("/next/") else "/next/workbench",
            }
        from fastapi.responses import RedirectResponse

        return RedirectResponse("/next/workbench")

    @app.post("/auth/logout")
    def auth_logout():
        return {"ok": True}

    import uvicorn

    host = os.environ.get("QYUNSLATION_BROWSER_HOST", "127.0.0.1")
    port = int(os.environ.get("QYUNSLATION_BROWSER_PORT", "8787"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

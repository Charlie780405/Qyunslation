#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""本机 127.0.0.1:8765，只提供 /dl/<token>/文件。Caddy /dl/* 反代到这里。"""
from __future__ import annotations

import posixpath
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path("/home/dev/pdf2zh/public-dl").resolve()
HOST = "127.0.0.1"
PORT = 8765


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def list_directory(self, path: str):
        self.send_error(403, "Forbidden")
        return None

    def translate_path(self, path: str) -> str:
        raw = unquote(urlparse(path).path)
        if raw.startswith("/dl/"):
            raw = raw[4:]
        rel = posixpath.normpath(raw).lstrip("/")
        if not rel or rel.startswith(".."):
            return str(ROOT / ".missing")
        target = (ROOT / rel).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            return str(ROOT / ".missing")
        return str(target)

    def end_headers(self) -> None:
        name = Path(unquote(urlparse(self.path).path)).name
        if name:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{name}"'
            )
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()

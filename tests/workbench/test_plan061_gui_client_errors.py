# SPDX-License-Identifier: MPL-2.0
"""PLAN-061：桥接异常保留 HTTP 状态，供保存提示分级。"""
from __future__ import annotations

import httpx

from qyunslation.workbench import gui_client


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_bridge_request_keeps_http_status(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_TERM_BRIDGE_SECRET", "secret")
    monkeypatch.setattr(gui_client, "sign_bridge_request", lambda **_kwargs: {})

    def boom(*_args, **_kwargs):
        request = httpx.Request("POST", "http://127.0.0.1/internal/workbench/v1/x")
        response = httpx.Response(403, request=request, json={"detail": "term_admin role required"})
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)

    monkeypatch.setattr(gui_client.httpx, "request", boom)
    try:
        gui_client._bridge_request("POST", "/internal/workbench/v1/x", {})
    except gui_client.WorkbenchTermBridgeUnavailable as exc:
        assert exc.status_code == 403
        assert "term_admin" in (exc.detail or "")
    else:
        raise AssertionError("expected WorkbenchTermBridgeUnavailable")

#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""SSE 断连后找回已完成翻译：服务端探针 + stale-guard 轮询。

1. translate_files 写入 pdf2zh_files/{session}/.qy-recover.json
2. middleware 暴露 GET /qy/recover/{session_id} 与 /qy/recover-by-stem/{stem}
   （Gradio launch 会重建 app，@demo.app.get 会失效，故走 middleware）
3. stale-guard 断连后轮询 recover，就绪则提示刷新/下载
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

MARKER = "_qy_sse_recover"
MW_MARKER = "_qy_sse_recover_mw"
JS_MARKER = "_qy_sse_recover_js"
JS_END = JS_MARKER + "_end"
STALE_GUARD_END = "  // _qy_stale_guard_js_end"

ROUTE_ANCHOR = "\ndef parse_user_passwd(file_path: str, welcome_page: str) -> tuple[list, str]:"

HELPER_BLOCK = '''
# _qy_sse_recover
def _qy_write_recover_manifest(session_id: str, *, ready: bool = False, stems=None, mono=None, dual=None) -> None:
    import json
    import time
    from pathlib import Path as _P

    sid = str(session_id or "").strip()
    if not sid or "/" in sid or ".." in sid:
        return
    session_dir = _P("pdf2zh_files") / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / ".qy-recover.json"
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if stems is not None:
        data["stems"] = list(stems)
    if not data.get("started_at"):
        data["started_at"] = time.time()
    data["session_id"] = sid
    data["ready"] = bool(ready)
    if ready:
        data["completed_at"] = time.time()
    if mono:
        data["mono"] = str(mono)
    if dual:
        data["dual"] = str(dual)
    try:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _qy_probe_session_outputs(session_id: str) -> dict:
    import json
    from pathlib import Path as _P

    sid = str(session_id or "").strip()
    if not sid or "/" in sid or ".." in sid:
        return {"ready": False}
    session_dir = _P("pdf2zh_files") / sid
    if not session_dir.is_dir():
        return {"ready": False, "session_id": sid}
    manifest = session_dir / ".qy-recover.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("ready"):
                return data
        except Exception:
            pass
    mono = dual = None
    for p in sorted(session_dir.glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True):
        name = p.name.lower()
        if "dual" in name and dual is None:
            dual = str(p.resolve())
        elif ("mono" in name or "no_watermark" in name) and mono is None and "dual" not in name:
            mono = str(p.resolve())
    if mono or dual:
        return {"ready": True, "session_id": sid, "mono": mono, "dual": dual}
    return {"ready": False, "session_id": sid}


def _qy_probe_outputs_by_stem(stem: str) -> dict:
    import json
    from pathlib import Path as _P

    key = str(stem or "").strip()
    if not key or "/" in key or ".." in key:
        return {"ready": False}
    base = _P("pdf2zh_files")
    if not base.is_dir():
        return {"ready": False}
    best = None
    best_ts = 0.0
    for session_dir in base.iterdir():
        if not session_dir.is_dir() or session_dir.name.startswith("."):
            continue
        manifest = session_dir / ".qy-recover.json"
        data = None
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:
                data = None
        if data and data.get("ready"):
            stems = data.get("stems") or []
            if any(key in str(s) or str(s).startswith(key) for s in stems):
                ts = float(data.get("completed_at") or data.get("started_at") or 0)
                if ts >= best_ts:
                    best_ts = ts
                    best = data
                continue
        for p in session_dir.glob("*.pdf"):
            if key not in p.name:
                continue
            ts = p.stat().st_mtime
            if ts < best_ts:
                continue
            probe = _qy_probe_session_outputs(session_dir.name)
            if probe.get("ready"):
                best_ts = ts
                best = probe
    return best or {"ready": False}

'''

MW_DISPATCH_OLD = '''    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path in _QY_NO_STORE_PATHS:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response'''

MW_DISPATCH_NEW = '''    async def dispatch(self, request, call_next):
        # _qy_sse_recover_mw
        path = request.url.path
        if path.startswith("/qy/recover-by-stem/"):
            from starlette.responses import JSONResponse
            from urllib.parse import unquote

            stem = unquote(path.split("/qy/recover-by-stem/", 1)[-1])
            return JSONResponse(_qy_probe_outputs_by_stem(stem))
        if path.startswith("/qy/recover/"):
            from starlette.responses import JSONResponse
            from urllib.parse import unquote

            session_id = unquote(path.split("/qy/recover/", 1)[-1])
            return JSONResponse(_qy_probe_session_outputs(session_id))
        response = await call_next(request)
        if request.url.path in _QY_NO_STORE_PATHS:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response'''

TRANSLATE_START_PATCH = '''    output_dir = Path("pdf2zh_files") / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # _qy_sse_recover_start
    try:
        _stems = []
        for _uf in (file_input or []):
            _stems.append(getattr(_uf, "orig_name", None) or getattr(_uf, "name", None) or str(_uf))
        _qy_write_recover_manifest(session_id, ready=False, stems=_stems)
    except Exception:
        pass
'''

TRANSLATE_START_OLD = '''    output_dir = Path("pdf2zh_files") / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
'''

FINALIZE_PATCH = '''        progress(1.0, desc=_("All translations complete!"))

        # _qy_sse_recover_done
        try:
            _last = state["file_order"][-1] if state.get("file_order") else None
            _res = state["results"].get(_last) if _last else None
            _qy_write_recover_manifest(
                session_id,
                ready=True,
                stems=[Path(n).stem for n in (state.get("file_order") or [])],
                mono=_res.get("mono") if _res else None,
                dual=_res.get("dual") if _res else None,
            )
        except Exception:
            pass

        # Final UI State'''

FINALIZE_OLD = '''        progress(1.0, desc=_("All translations complete!"))

        # Final UI State'''

JS_BLOCK = r"""
    // _qy_sse_recover_js
    function _qyCurrentStem() {
      var text = '';
      document.querySelectorAll('.uploaded-files-list p, .uploaded-files-list').forEach(function (el) {
        text += (el.textContent || '') + '\\n';
      });
      var m = text.match(/([\\w\\-. ]+\\.pdf)/i);
      if (m) return m[1].replace(/^\\d+\\.\\s*/, '').trim();
      var dd = document.querySelector('[data-testid="dropdown"] select, select');
      if (dd && dd.value) return String(dd.value).replace(/_mono|_dual.*$/i, '').trim();
      return '';
    }

    function _qyPollRecover(onReady) {
      var stem = _qyCurrentStem();
      var tries = 0;
      var maxTries = 24;
      function tick() {
        tries++;
        if (!stem) return;
        var url = '/qy/recover-by-stem/' + encodeURIComponent(stem.replace(/\\.pdf$/i, ''));
        fetch(url, { cache: 'no-store' })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data && data.ready) {
              onReady(data, stem);
            } else if (tries < maxTries) {
              setTimeout(tick, 5000);
            }
          })
          .catch(function () {
            if (tries < maxTries) setTimeout(tick, 5000);
          });
      }
      tick();
    }

    var _qyOrigShowBanner = showBanner;
    showBanner = function (msg) {
      if (msg.indexOf('\u8fde\u63a5\u4e2d\u65ad') >= 0) {
        _qyOrigShowBanner(
          msg + ' \u82e5\u540e\u53f0\u5df2\u5b8c\u6210\uff0c\u53ef\u5237\u65b0\u9875\u9762\u67e5\u770b\u4e0b\u8f7d\u533a\u3002'
        );
        _qyPollRecover(function () {
          if (!banner) return;
          var hint = document.createElement('span');
          hint.style.marginLeft = '8px';
          hint.textContent = '\u5df2\u68c0\u6d4b\u5230\u5b8c\u6210\u7684\u8bd1\u6587\uff0c\u8bf7\u5237\u65b0\u9875\u9762\u3002';
          banner.appendChild(hint);
        });
        return;
      }
      _qyOrigShowBanner(msg);
    };
    // _qy_sse_recover_js_end
"""

JS_MISPLACED_RE = re.compile(
    r"\n[ \t]*// _qy_stale_guard_js_end\n[ \t]*// _qy_sse_recover_js\n.*?\n[ \t]*// _qy_sse_recover_js_end\n",
    re.S,
)
JS_INSERT_BEFORE = "    var origFetch = window.fetch;"
DEMO_ROUTE_RE = re.compile(
    r"\n@demo\.app\.get\(\"/qy/recover/\{session_id\}\"\)\nasync def _qy_recover_session.*?"
    r"\n@demo\.app\.get\(\"/qy/recover-by-stem/\{stem\}\"\)\nasync def _qy_recover_by_stem.*?\n",
    re.S,
)


def apply_helpers(text: str) -> tuple[str, bool]:
    if "_qy_write_recover_manifest" in text:
        return text, False
    if ROUTE_ANCHOR not in text:
        print("WARNING: parse_user_passwd anchor missing", file=sys.stderr)
        return text, False
    return text.replace(ROUTE_ANCHOR, "\n" + HELPER_BLOCK + ROUTE_ANCHOR, 1), True


def apply_middleware(text: str) -> tuple[str, bool]:
    if MW_MARKER in text:
        return text, False
    if MW_DISPATCH_OLD not in text:
        print("WARNING: no-store middleware dispatch missing", file=sys.stderr)
        return text, False
    return text.replace(MW_DISPATCH_OLD, MW_DISPATCH_NEW, 1), True


def remove_demo_routes(text: str) -> tuple[str, bool]:
    if "@demo.app.get(\"/qy/recover/{session_id}\")" not in text:
        return text, False
    new_text, n = DEMO_ROUTE_RE.subn("\n", text)
    return new_text, n > 0


def apply_translate_hooks(text: str) -> tuple[str, bool]:
    changed = False
    if "# _qy_sse_recover_start" not in text and TRANSLATE_START_OLD in text:
        text = text.replace(TRANSLATE_START_OLD, TRANSLATE_START_PATCH, 1)
        changed = True
    if "# _qy_sse_recover_done" not in text and FINALIZE_OLD in text:
        text = text.replace(FINALIZE_OLD, FINALIZE_PATCH, 1)
        changed = True
    return text, changed


def apply_js(text: str) -> tuple[str, bool]:
    changed = False
    m_bad = JS_MISPLACED_RE.search(text)
    if m_bad:
        text = text[: m_bad.start()] + "\n  // _qy_stale_guard_js_end\n" + text[m_bad.end() :]
        changed = True

    inner_re = re.compile(
        r"\n[ \t]*// _qy_sse_recover_js\n.*?\n[ \t]*// _qy_sse_recover_js_end\n",
        re.S,
    )
    m = inner_re.search(text)
    if m:
        if m.group(0).rstrip() != JS_BLOCK.rstrip():
            text = text[: m.start()] + JS_BLOCK.rstrip() + "\n" + text[m.end() :]
            changed = True
        return text, changed

    if JS_INSERT_BEFORE in text:
        text = text.replace(JS_INSERT_BEFORE, JS_BLOCK + JS_INSERT_BEFORE, 1)
        changed = True
    return text, changed


def apply(text: str) -> tuple[str, bool]:
    changed = False
    for fn in (apply_helpers, remove_demo_routes, apply_middleware, apply_translate_hooks, apply_js):
        text, c = fn(text)
        changed = changed or c
    return text, changed


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"FAIL: {msg}", file=sys.stderr)
            errs += 1

    need("_qy_write_recover_manifest" in text, "recover helper missing")
    need(MW_MARKER in text, "recover middleware missing")
    need("@demo.app.get(\"/qy/recover/{session_id}\")" not in text, "demo routes must not remain")
    need("# _qy_sse_recover_start" in text, "recover start hook missing")
    need("# _qy_sse_recover_done" in text, "recover done hook missing")
    need(text.count("// " + JS_MARKER + "\n") == 1, "recover js missing or duplicated")
    need(text.count("// " + JS_END) == 1, "recover js end missing or duplicated")
    need("text += (el.textContent || '') + '\\\\n';" in text, "recover js newline must stay escaped")
    js_pos = text.find("// " + JS_MARKER)
    fetch_pos = text.find("var origFetch = window.fetch;")
    need(js_pos >= 0 and fetch_pos >= 0 and js_pos < fetch_pos, "recover js must precede fetch wrapper")
    try:
        compile(text, str(GUI), "exec")
    except SyntaxError as e:
        print(f"FAIL: syntax {e}", file=sys.stderr)
        errs += 1
    return errs


def main() -> int:
    if not GUI.is_file():
        print(f"ERROR: missing {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    updated, changed = apply(original)
    if changed:
        GUI.write_text(updated, encoding="utf-8")
        print("patched:", GUI)
    else:
        print("already patched:", GUI)
    errs = verify(GUI.read_text(encoding="utf-8"))
    if errs:
        print(f"verify failed: {errs} error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

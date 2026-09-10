#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-040a：固定 Gradio cookie_id、持久化登录 token、401 重新登录横幅。

须在 apply-pdf2zh-stale-guard.py 之后跑（会改写 stale-guard JS 块）。
"""
from __future__ import annotations

import os
import re
import secrets
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
ROUTES = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/gradio/routes.py"
)
COOKIE_FILE = Path("/home/dev/pdf2zh/gradio.cookie_id")
TOKEN_FILE = Path("/home/dev/pdf2zh/gradio-tokens.json")
MARKER = "PLAN-040a: stable cookie_id"

AUTH_MSG = (
    '<div style="font-family:system-ui,sans-serif;padding:12px 4px">'
    "<strong>Qyunslation</strong><br/>"
    "请登录后继续。服务重启后若无法操作，请重新登录。"
    "</div>"
)


def ensure_cookie_id() -> str:
    env = (os.environ.get("QYUNSLATION_GRADIO_COOKIE_ID") or "").strip()
    if env:
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not COOKIE_FILE.is_file() or COOKIE_FILE.read_text().strip() != env:
            COOKIE_FILE.write_text(env + "\n", encoding="utf-8")
        return env
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if COOKIE_FILE.is_file():
        existing = COOKIE_FILE.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    cid = secrets.token_urlsafe(32)
    COOKIE_FILE.write_text(cid + "\n", encoding="utf-8")
    return cid


def patch_routes(text: str, cookie_id: str) -> tuple[str, bool]:
    changed = False
    # --- cookie_id ---
    old_cookie = "        self.cookie_id = secrets.token_urlsafe(32)\n"
    new_cookie = (
        f"        # {MARKER}\n"
        f"        self.cookie_id = (\n"
        f'            os.environ.get("QYUNSLATION_GRADIO_COOKIE_ID")\n'
        f'            or Path("/home/dev/pdf2zh/gradio.cookie_id").read_text(encoding="utf-8").strip()\n'
        f"            if Path('/home/dev/pdf2zh/gradio.cookie_id').is_file()\n"
        f"            else None\n"
        f"        ) or secrets.token_urlsafe(32)\n"
        f"        if not self.cookie_id:\n"
        f"            self.cookie_id = secrets.token_urlsafe(32)\n"
    )
    # Simpler stable assignment:
    new_cookie = (
        f"        # {MARKER}\n"
        f'        _qy_cid = (os.environ.get("QYUNSLATION_GRADIO_COOKIE_ID") or "").strip()\n'
        f"        if not _qy_cid:\n"
        f'            _qy_cf = Path("/home/dev/pdf2zh/gradio.cookie_id")\n'
        f"            if _qy_cf.is_file():\n"
        f'                _qy_cid = _qy_cf.read_text(encoding="utf-8").strip()\n'
        f"        self.cookie_id = _qy_cid or secrets.token_urlsafe(32)\n"
    )
    if MARKER not in text:
        if old_cookie not in text:
            # already custom?
            if "self.cookie_id = _qy_cid" not in text:
                print("WARNING: cookie_id anchor missing", file=sys.stderr)
            else:
                pass
        else:
            text = text.replace(old_cookie, new_cookie, 1)
            changed = True
        # ensure Path import
        if "from pathlib import Path" not in text.split("class App")[0]:
            text = text.replace(
                "from pathlib import Path\n",
                "from pathlib import Path\n",
                1,
            )
            if "from pathlib import Path" not in text[:2000]:
                text = text.replace(
                    "import secrets\n",
                    "import secrets\nfrom pathlib import Path\n",
                    1,
                )
                changed = True
    else:
        # refresh cookie block if needed
        pass

    # --- token load in configure_app (not __init__: configure_app resets tokens) ---
    token_marker = "PLAN-040a: persist tokens"
    old_cfg_tokens = (
        "        self.favicon_path = blocks.favicon_path\n"
        "        self.tokens = {}\n"
        "        self.root_path = blocks.root_path or blocks.custom_mount_path or \"\"\n"
    )
    new_cfg_tokens = (
        "        self.favicon_path = blocks.favicon_path\n"
        f"        # {token_marker}\n"
        "        self.tokens = {}\n"
        '        _qy_tf = Path("/home/dev/pdf2zh/gradio-tokens.json")\n'
        "        if _qy_tf.is_file():\n"
        "            try:\n"
        "                import json as _qy_json\n"
        "\n"
        '                loaded = _qy_json.loads(_qy_tf.read_text(encoding="utf-8"))\n'
        "                if isinstance(loaded, dict):\n"
        "                    self.tokens = loaded\n"
        "            except Exception:\n"
        "                self.tokens = {}\n"
        '        self.root_path = blocks.root_path or blocks.custom_mount_path or ""\n'
    )
    if token_marker not in text and old_cfg_tokens in text:
        text = text.replace(old_cfg_tokens, new_cfg_tokens, 1)
        changed = True

    # after successful login set_cookie, persist
    login_save_anchor = (
        '                response.set_cookie(\n'
        '                    key=f"access-token-unsecure-{app.cookie_id}",\n'
        "                    value=token,\n"
        "                    httponly=True,\n"
        "                )\n"
        "                return response\n"
    )
    login_save_new = (
        '                response.set_cookie(\n'
        '                    key=f"access-token-unsecure-{app.cookie_id}",\n'
        "                    value=token,\n"
        "                    httponly=True,\n"
        "                )\n"
        f"                # {token_marker} save\n"
        "                try:\n"
        "                    import json as _qy_json\n"
        '                    Path("/home/dev/pdf2zh/gradio-tokens.json").write_text(\n'
        '                        _qy_json.dumps(app.tokens, ensure_ascii=False), encoding="utf-8"\n'
        "                    )\n"
        "                except Exception:\n"
        "                    pass\n"
        "                return response\n"
    )
    if f"{token_marker} save" not in text and login_save_anchor in text:
        text = text.replace(login_save_anchor, login_save_new, 1)
        changed = True

    text2, c2 = patch_short_login_page(text)
    return text2, changed or c2


SHORT_LOGIN_MARKER = "PLAN-040a: short login page"

SHORT_LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Qyunslation 登录</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;
font-family:system-ui,sans-serif;background:linear-gradient(160deg,#f2f5f8,#e4ebe7 55%,#dfe8f0)}
form{width:min(360px,92vw);padding:28px 24px;background:#fff;border:1px solid #d5dde5;
border-radius:12px;box-shadow:0 10px 30px rgba(20,40,60,.08)}
h1{margin:0 0 6px;font-size:1.35rem;letter-spacing:.02em}
p.sub{margin:0 0 18px;color:#5b6b7a;font-size:.92rem;line-height:1.45}
label{display:block;margin:10px 0 4px;font-size:.82rem;color:#3d4d5c}
input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #c5d0db;
border-radius:8px;font-size:1rem}
button{margin-top:16px;width:100%;padding:11px 14px;border:0;border-radius:8px;
background:#1f4e79;color:#fff;font-size:1rem;cursor:pointer}
button:hover{background:#183d5f}
#err{min-height:1.2em;margin:10px 0 0;color:#b42318;font-size:.88rem}
.msg{margin:0 0 14px;padding:10px 12px;background:#f4f7fa;border-radius:8px;
color:#334155;font-size:.88rem}
</style></head><body>
<form id="f" autocomplete="on">
<h1>Qyunslation</h1>
<p class="sub">请登录后继续。服务重启后若无法操作，请重新登录。</p>
__AUTH_MSG_BLOCK__
<label for="u">用户名</label>
<input id="u" name="username" required autofocus/>
<label for="p">密码</label>
<input id="p" name="password" type="password" required/>
<button type="submit">登录</button>
<p id="err"></p>
</form>
<script>
document.getElementById('f').addEventListener('submit', async function (e) {
  e.preventDefault();
  var err = document.getElementById('err');
  err.textContent = '';
  try {
    var body = new URLSearchParams(new FormData(e.target));
    var r = await fetch('/login', {
      method: 'POST',
      body: body,
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/x-www-form-urlencoded'}
    });
    if (r.ok) { location.href = '/'; return; }
    err.textContent = '登录失败（' + r.status + '），请检查账号密码。';
  } catch (x) {
    err.textContent = '网络错误，请重试。';
  }
});
</script>
</body></html>
"""


def patch_short_login_page(text: str) -> tuple[str, bool]:
    """未登录 GET / 返回短登录页，不再吐整棵 Gradio 壳。"""
    if SHORT_LOGIN_MARKER in text and "_QY_SHORT_LOGIN_HTML" in text:
        return text, False

    old_else = '''            else:
                config = {
                    "auth_required": True,
                    "auth_message": blocks.auth_message,
                    "space_id": blocks.space_id,
                    "root": root,
                    "page": {"": {"layout": {}}},
                    "pages": [""],
                    "components": [],
                    "dependencies": [],
                    "current_page": "",
                }

            try:
                template = (
                    "frontend/share.html" if blocks.share else "frontend/index.html"
                )
                gradio_api_info = api_info(request)
                resp = templates.TemplateResponse(
                    request=request,
                    name=template,
                    context={
                        "config": config,
                        "gradio_api_info": gradio_api_info,
                    },
                )
                return resp
'''
    new_else = '''            else:
                # PLAN-040a: short login page
                _msg = (blocks.auth_message or "").strip()
                _msg_block = (
                    f'<div class="msg">{_msg}</div>' if _msg else ""
                )
                _html = _QY_SHORT_LOGIN_HTML.replace("__AUTH_MSG_BLOCK__", _msg_block)
                return HTMLResponse(
                    content=_html,
                    media_type="text/html; charset=utf-8",
                    headers={
                        "Cache-Control": "no-store, no-cache, must-revalidate",
                        "Pragma": "no-cache",
                    },
                )

            try:
                template = (
                    "frontend/share.html" if blocks.share else "frontend/index.html"
                )
                gradio_api_info = api_info(request)
                resp = templates.TemplateResponse(
                    request=request,
                    name=template,
                    context={
                        "config": config,
                        "gradio_api_info": gradio_api_info,
                    },
                )
                return resp
'''
    if old_else not in text:
        print("WARNING: short-login else-branch anchor missing", file=sys.stderr)
        return text, False

    const_anchor = '        @app.head("/", response_class=HTMLResponse)\n'
    const_block = (
        f"        # {SHORT_LOGIN_MARKER} html\n"
        f"        _QY_SHORT_LOGIN_HTML = {SHORT_LOGIN_HTML!r}\n\n"
        + const_anchor
    )
    if "_QY_SHORT_LOGIN_HTML" not in text:
        if const_anchor not in text:
            print("WARNING: short-login const anchor missing", file=sys.stderr)
            return text, False
        text = text.replace(const_anchor, const_block, 1)

    text = text.replace(old_else, new_else, 1)
    return text, True


def patch_gui_auth_message(text: str) -> tuple[str, bool]:
    """空 welcome_page 时注入默认中文 auth_message。"""
    marker = "PLAN-040a: default auth_message"
    if marker in text:
        return text, False
    old = "    user_list, html = parse_user_passwd(auth_file, welcome_page)\n\n    if not auth_file or not user_list:"
    new = (
        "    user_list, html = parse_user_passwd(auth_file, welcome_page)\n"
        f"    # {marker}\n"
        "    if auth_file and user_list and not (html or '').strip():\n"
        f"        html = {AUTH_MSG!r}\n\n"
        "    if not auth_file or not user_list:"
    )
    if old not in text:
        print("WARNING: auth_message anchor missing", file=sys.stderr)
        return text, False
    return text.replace(old, new, 1), True


STALE_401_SNIPPET = """
    function checkAuth() {
      fetch('/config', { cache: 'no-store', credentials: 'same-origin' })
        .then(function (r) {
          if (r.status === 401) {
            showBanner('\\u8bf7\\u91cd\\u65b0\\u767b\\u5f55\\uff1a\\u4f1a\\u8bdd\\u5df2\\u5931\\u6548\\u6216\\u670d\\u52a1\\u521a\\u91cd\\u542f\\u3002');
            if (banner) {
              var b = banner.querySelector('button');
              if (b) b.textContent = '\\u5237\\u65b0\\u5e76\\u767b\\u5f55';
            }
            return null;
          }
          return r.json();
        })
        .then(function (cfg) {
          if (!cfg) return;
          if (cfg.auth_required) {
            showBanner('\\u8bf7\\u767b\\u5f55\\u540e\\u4f7f\\u7528 Qyunslation\\u3002');
            return;
          }
          if (APP_ID && cfg.app_id && cfg.app_id !== APP_ID) {
            showBanner('\\u670d\\u52a1\\u5df2\\u66f4\\u65b0\\uff0c\\u5f53\\u524d\\u9875\\u9762\\u7684\\u754c\\u9762\\u7248\\u672c\\u5df2\\u8fc7\\u671f\\uff0c\\u64cd\\u4f5c\\u4e0d\\u4f1a\\u751f\\u6548\\u3002');
          }
        })
        .catch(function () {});
    }
    checkAuth();
    setInterval(checkAuth, 30000);
"""


def patch_stale_guard_js(text: str) -> tuple[str, bool]:
    """替换 checkAppId 为 checkAuth（含 401）。"""
    if "function checkAuth()" in text and "r.status === 401" in text:
        return text, False
    # Replace the checkAppId function + calls
    old = """    // 服务重启会换 app_id，此时页面里的组件树与事件索引已过期
    function checkAppId() {
      if (!APP_ID) return;
      fetch('/config', { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (cfg) {
          if (cfg && cfg.app_id && cfg.app_id !== APP_ID) {
            showBanner('\\u670d\\u52a1\\u5df2\\u66f4\\u65b0\\uff0c\\u5f53\\u524d\\u9875\\u9762\\u7684\\u754c\\u9762\\u7248\\u672c\\u5df2\\u8fc7\\u671f\\uff0c\\u64cd\\u4f5c\\u4e0d\\u4f1a\\u751f\\u6548\\u3002');
          }
        })
        .catch(function () {});
    }
    checkAppId();
    setInterval(checkAppId, 30000);
"""
    if old not in text:
        # try already-patched or different whitespace
        if "r.status === 401" in text:
            return text, False
        print("WARNING: stale-guard checkAppId block missing", file=sys.stderr)
        return text, False
    return text.replace(old, STALE_401_SNIPPET.lstrip("\n"), 1), True


def patch_fetch_401(text: str) -> tuple[str, bool]:
    """queue/join 401 时提示重新登录。"""
    marker = "PLAN-040a: fetch 401"
    if marker in text:
        return text, False
    old = """    var origFetch = window.fetch;
    window.fetch = function (input) {
      var url = String((input && input.url) || input || '');
      var p = origFetch.apply(this, arguments);
      if (url.indexOf('/queue/join') >= 0) {
        pending++;
      } else if (url.indexOf('/queue/data') >= 0) {
        lastDataOpen = Date.now();
        p.then(watchStream).catch(function () {});
      }
      return p;
    };
"""
    new = """    var origFetch = window.fetch;
    window.fetch = function (input) {
      // """ + marker + """
      var url = String((input && input.url) || input || '');
      var p = origFetch.apply(this, arguments);
      if (url.indexOf('/queue/join') >= 0) {
        pending++;
        p.then(function (r) {
          if (r && r.status === 401) {
            showBanner('\\u8bf7\\u91cd\\u65b0\\u767b\\u5f55\\uff1a\\u4e0a\\u4f20/\\u961f\\u5217\\u8bf7\\u6c42\\u672a\\u6388\\u6743\\u3002');
          }
        }).catch(function () {});
      } else if (url.indexOf('/queue/data') >= 0) {
        lastDataOpen = Date.now();
        p.then(watchStream).catch(function () {});
      } else if (url.indexOf('/gradio_api/upload') >= 0) {
        p.then(function (r) {
          if (r && r.status === 401) {
            showBanner('\\u8bf7\\u91cd\\u65b0\\u767b\\u5f55\\uff1a\\u4e0a\\u4f20\\u672a\\u6388\\u6743\\u3002');
          }
        }).catch(function () {});
      }
      return p;
    };
"""
    if old not in text:
        print("WARNING: fetch wrapper anchor missing", file=sys.stderr)
        return text, False
    return text.replace(old, new, 1), True


def main() -> int:
    cid = ensure_cookie_id()
    print(f"cookie_id={cid[:8]}… file={COOKIE_FILE}")

    if not ROUTES.is_file():
        print(f"ERROR: missing {ROUTES}", file=sys.stderr)
        return 1
    routes = ROUTES.read_text(encoding="utf-8")
    routes2, c1 = patch_routes(routes, cid)
    if c1:
        ROUTES.write_text(routes2, encoding="utf-8")
        print(f"patched: {ROUTES}")
    else:
        print(f"unchanged routes (or already patched): {ROUTES}")

    if not GUI.is_file():
        print(f"ERROR: missing {GUI}", file=sys.stderr)
        return 1
    gui = GUI.read_text(encoding="utf-8")
    changed = False
    for fn in (patch_gui_auth_message, patch_stale_guard_js, patch_fetch_401):
        gui, c = fn(gui)
        changed = changed or c
    if changed:
        GUI.write_text(gui, encoding="utf-8")
        print(f"patched: {GUI}")
    else:
        print(f"unchanged gui: {GUI}")

    # sanity
    routes_now = ROUTES.read_text(encoding="utf-8")
    gui_now = GUI.read_text(encoding="utf-8")
    errs = 0
    if MARKER not in routes_now and "self.cookie_id = _qy_cid" not in routes_now:
        print("ERROR: routes cookie_id not patched", file=sys.stderr)
        errs += 1
    if "PLAN-040a: persist tokens" not in routes_now:
        print("ERROR: token persist not patched", file=sys.stderr)
        errs += 1
    if SHORT_LOGIN_MARKER not in routes_now or "_QY_SHORT_LOGIN_HTML" not in routes_now:
        print("ERROR: short login page not patched", file=sys.stderr)
        errs += 1
    if "r.status === 401" not in gui_now:
        print("ERROR: stale-guard 401 not patched", file=sys.stderr)
        errs += 1
    try:
        compile(gui_now, str(GUI), "exec")
        compile(routes_now, str(ROUTES), "exec")
    except SyntaxError as e:
        print(f"ERROR: syntax: {e}", file=sys.stderr)
        errs += 1
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())

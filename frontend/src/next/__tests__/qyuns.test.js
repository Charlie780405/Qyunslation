import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import { appbarScriptUrl, displayName, shouldShowAppbar, syncAppbar } from '../qyuns/appbar-mount.js';
import { DEFAULT_END_SESSION_URL, LOGOUT_PATH, PLATFORM_HOSTS, checkNext, readCsrf, resolveLogoutTarget, runQyunsLogout } from '../qyuns/logout.js';

const here = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(here, '../../..');
const ORIGIN = 'https://translate.qyunsgen.com';

describe('qyuns logout allowlist', () => {
  it('没有 next：Authentik 的 qyunslation end-session 页；可覆盖', () => {
    expect(resolveLogoutTarget(undefined, ORIGIN)).toEqual({ ok: true, url: DEFAULT_END_SESSION_URL });
    expect(resolveLogoutTarget('', ORIGIN)).toEqual({ ok: true, url: DEFAULT_END_SESSION_URL });
    expect(DEFAULT_END_SESSION_URL).toBe('https://auth.qyunsgen.com/application/o/qyunslation/end-session/');
    expect(resolveLogoutTarget(null, ORIGIN, 'https://auth.qyunsgen.com/application/o/x/end-session/').url).toBe('https://auth.qyunsgen.com/application/o/x/end-session/');
  });

  it('允许：站内路径、四个平台主机、Authentik end-session 页', () => {
    expect(checkNext('/next/workbench?x=1', ORIGIN)).toEqual({ ok: true, url: `${ORIGIN}/next/workbench?x=1` });
    for (const h of ['apps', 'watch', 'weknora', 'translate']) expect(checkNext(`https://${h}.qyunsgen.com/x`, ORIGIN).ok).toBe(true);
    expect(checkNext('https://auth.qyunsgen.com/application/o/weknora/end-session/', ORIGIN).ok).toBe(true);
  });

  it('拒绝：外部域名、协议相对、反斜杠、控制字符、编码绕过、端口与用户信息、Authentik 其他路径', () => {
    const bad = [
      'https://evil.example/', 'https://evil.example@translate.qyunsgen.com/', 'https://translate.qyunsgen.com.evil.example/',
      'http://translate.qyunsgen.com/', 'https://translate.qyunsgen.com:8443/', 'https://u:p@translate.qyunsgen.com/',
      '//evil.example', '/\\evil.example', 'javascript:alert(1)', 'data:text/html,x', 'evil.example',
      'https://auth.qyunsgen.com/', 'https://auth.qyunsgen.com/application/o/x/', 'https://auth.qyunsgen.com/application/o/x/end-session',
      'https://homepage.qyunsgen.com/', 'https://qyunsgen.com/',
      '/%2f%2fevil.example', '/%5cevil.example', '/%E0%A4%A', '/a\nb', '/a\u0000b', 'x'.repeat(3000),
    ];
    for (const b of bad) expect(checkNext(b, ORIGIN).ok, JSON.stringify(b).slice(0, 50)).toBe(false);
    expect(resolveLogoutTarget(42, ORIGIN).ok).toBe(false);
  });

  it('白名单恰好是门户与三个 SSO 应用', () => {
    expect([...PLATFORM_HOSTS].sort()).toEqual(['apps.qyunsgen.com', 'translate.qyunsgen.com', 'watch.qyunsgen.com', 'weknora.qyunsgen.com']);
    expect(LOGOUT_PATH).toBe('/next/qyuns-logout');
  });
});

describe('qyuns logout flow', () => {
  const mk = (over = {}) => {
    const calls = [];
    return {
      calls,
      d: {
        next: 'https://watch.qyunsgen.com/api/qyunsapps/logout?next=/',
        origin: ORIGIN,
        cookie: 'foo=1; qyunslation_csrf=tok%2Fen; bar=2',
        fetchFn: async (url, init) => { calls.push(`fetch ${init.method} ${url} csrf=${init.headers['X-CSRF-Token']} ${init.credentials}`); return new Response(null, { status: 204 }); },
        replace: (u) => calls.push(`replace ${u}`),
        ...over,
      },
    };
  };

  it('readCsrf 与 api.js 的读取方式一致（解码、缺失返回空）', () => {
    expect(readCsrf('a=1; qyunslation_csrf=abc%2Fdef; b=2')).toBe('abc/def');
    expect(readCsrf('a=1')).toBe('');
    expect(readCsrf(undefined)).toBe('');
  });

  it('有效 next：POST /auth/logout 带 CSRF 头与同源凭据，随后整页跳转', async () => {
    const { d, calls } = mk();
    expect(await runQyunsLogout(d)).toEqual({ rejected: false, target: 'https://watch.qyunsgen.com/api/qyunsapps/logout?next=/' });
    expect(calls).toEqual(['fetch POST /auth/logout csrf=tok/en same-origin', 'replace https://watch.qyunsgen.com/api/qyunsapps/logout?next=/']);
  });

  it('没有 next：跳到 Authentik end-session', async () => {
    const { d, calls } = mk({ next: null });
    await runQyunsLogout(d);
    expect(calls.at(-1)).toBe(`replace ${DEFAULT_END_SESSION_URL}`);
  });

  it('无效 next：不调后端、不跳转', async () => {
    for (const bad of ['https://evil.example/', '//evil.example', 'javascript:alert(1)']) {
      const { d, calls } = mk({ next: bad });
      expect(await runQyunsLogout(d)).toMatchObject({ rejected: true });
      expect(calls).toEqual([]);
    }
  });

  it('后端不可达（fetch 抛错）也继续跳转', async () => {
    const { d, calls } = mk({ fetchFn: async () => { throw new Error('offline'); } });
    expect((await runQyunsLogout(d)).rejected).toBe(false);
    expect(calls).toEqual(['replace https://watch.qyunsgen.com/api/qyunsapps/logout?next=/']);
  });
});

describe('qyuns appbar mount', () => {
  afterEach(() => {
    document.querySelector('qyuns-appbar')?.remove();
    document.head.querySelectorAll('script[src$="qyuns-appbar.js"]').forEach((s) => s.remove());
    document.body.className = '';
  });

  it('只在平台主机、已登录、非预览、未被关闭时显示', () => {
    const base = { hostname: 'translate.qyunsgen.com', authenticated: true, isPreview: false, disabled: false };
    expect(shouldShowAppbar(base)).toBe(true);
    expect(shouldShowAppbar({ ...base, authenticated: false })).toBe(false);
    expect(shouldShowAppbar({ ...base, isPreview: true })).toBe(false);
    expect(shouldShowAppbar({ ...base, disabled: true })).toBe(false);
    for (const h of ['localhost', '127.0.0.1', 'watch.qyunsgen.com', 'translate.qyunsgen.com.evil.example']) expect(shouldShowAppbar({ ...base, hostname: h })).toBe(false);
  });

  it('脚本地址跟随 vite 的 base（/app-assets/），且是同源路径', () => {
    expect(appbarScriptUrl('/app-assets/')).toBe('/app-assets/qyuns-appbar.js');
    expect(appbarScriptUrl('/app-assets')).toBe('/app-assets/qyuns-appbar.js');
    expect(appbarScriptUrl()).toBe('/qyuns-appbar.js');
  });

  it('displayName：display_name 优先，其次 name、email，缺失为空', () => {
    expect(displayName({ display_name: 'A', name: 'B' })).toBe('A');
    expect(displayName({ name: 'B', email: 'c@x.com' })).toBe('B');
    expect(displayName({ email: 'c@x.com' })).toBe('c@x.com');
    expect(displayName(null)).toBe('');
  });

  it('syncAppbar：登录后插入顶栏与脚本并给 body 加类；退出后移除', () => {
    const env = { hostname: 'translate.qyunsgen.com', BASE_URL: '/app-assets/' };
    syncAppbar({ authenticated: true, isPreview: false, user: { display_name: 'Alice' } }, env);
    const bar = document.querySelector('qyuns-appbar');
    expect(bar).not.toBeNull();
    expect(document.body.firstChild).toBe(bar);
    expect(bar.getAttribute('current-app')).toBe('translate');
    expect(bar.getAttribute('logout-href')).toBe('/next/qyuns-logout');
    expect(bar.getAttribute('portal-href')).toBe('https://apps.qyunsgen.com/');
    expect(bar.getAttribute('theme')).toBe('light');
    expect(bar.getAttribute('user-name')).toBe('Alice');
    expect(document.head.querySelector('script[src="/app-assets/qyuns-appbar.js"]')).not.toBeNull();
    expect(document.body.classList.contains('qyuns-appbar-on')).toBe(true);
    syncAppbar({ authenticated: true, isPreview: false, user: { display_name: 'Alice' } }, env); // 幂等
    expect(document.querySelectorAll('qyuns-appbar').length).toBe(1);
    expect(document.head.querySelectorAll('script[src="/app-assets/qyuns-appbar.js"]').length).toBe(1);
    syncAppbar({ authenticated: false }, env);
    expect(document.querySelector('qyuns-appbar')).toBeNull();
    expect(document.body.classList.contains('qyuns-appbar-on')).toBe(false);
  });

  it('syncAppbar：非平台主机（本地开发等）什么都不挂', () => {
    syncAppbar({ authenticated: true, isPreview: false, user: { name: 'x' } }, { hostname: 'localhost', BASE_URL: '/' });
    expect(document.querySelector('qyuns-appbar')).toBeNull();
    expect(document.body.className).toBe('');
  });
});

describe('qyuns vendored files and wiring', () => {
  const manifest = JSON.parse(readFileSync(join(frontend, 'src/next/vendor/qyunsapps-vendored.json'), 'utf8'));
  const HEADER = /^\/\* generated from QyunsApps@\S+ \((?:appbar built with )?tokens sha256:[0-9a-f]{12}\) — do not edit \*\/\n/;

  it('清单列出令牌 CSS、Tailwind 3 preset 与顶栏脚本', () => {
    expect(Object.keys(manifest.files).sort()).toEqual(['frontend/public/qyuns-appbar.js', 'frontend/src/next/vendor/tokens.css', 'frontend/src/next/vendor/tw3-preset.cjs']);
  });

  it.each(Object.entries(manifest.files))('%s 带 generated 头，且正文与清单一致（没有人手改）', (rel, expected) => {
    const text = readFileSync(join(frontend, '..', rel), 'utf8');
    expect(text).toMatch(HEADER);
    expect(createHash('sha256').update(text.replace(HEADER, '')).digest('hex')).toBe(expected);
  });

  it('main.js：@/qyuns 在 next.css 之后导入；installQyuns 处理退出后不再启动应用', () => {
    const main = readFileSync(join(frontend, 'src/main.js'), 'utf8');
    expect(main.indexOf("./next/qyuns/index.js")).toBeGreaterThan(main.indexOf("./next/next.css"));
    expect(main).toMatch(/if \(installQyuns\(nextRouter\)\) \{[\s\S]*?\} else if \(isNextSurface\) \{/);
  });

  it('Tailwind 配置引入生成的 preset；AppShell 退出会结束 Authentik 会话（开发模式除外）', () => {
    expect(readFileSync(join(frontend, 'tailwind.config.js'), 'utf8')).toMatch(/presets: \[qyunsappsPreset\]/);
    const shell = readFileSync(join(frontend, 'src/next/components/AppShell.vue'), 'utf8');
    expect(shell).toMatch(/window\.location\.assign\(import\.meta\.env\.VITE_QYUNSAPPS_END_SESSION_URL \|\| DEFAULT_END_SESSION_URL\)/);
    expect(shell).toMatch(/if \(import\.meta\.env\.DEV\) router\.push\(\{ name: 'login' \}\)/);
  });

  it('qyuns.css 映射主色并给两处 100vh 让出顶栏高度', () => {
    const css = readFileSync(join(frontend, 'src/next/qyuns/qyuns.css'), 'utf8');
    expect(css).toMatch(/--qy-primary: var\(--qa-color-brand-600\);/);
    expect(css).toMatch(/body\.qyuns-appbar-on \.qy-app-shell \{ min-height: calc\(100vh - /);
    expect(css).toMatch(/body\.qyuns-appbar-on \.qy-body \{ min-height: calc\(100vh - 64px - /);
  });
});

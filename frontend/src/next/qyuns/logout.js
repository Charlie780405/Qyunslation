// QyunsApps 统一退出（PLAN-077 T2 / QyunsApps PLAN-001i、ADR-005）。
// /next/qyuns-logout?next=… 清除本应用会话，然后跳到 next（下一环）；没有 next 时跳到 Authentik 的 end-session 页。
// 注意：Authentik 2025.10.4 的 end-session 不支持 post_logout_redirect_uri / id_token_hint，只会跑 invalidation flow 并停在"已退出"页，
// 所以"回到门户"只能靠门户的重定向链（每一环都是一个本类路由），不能靠 IdP 回跳。

// 平台主机白名单：门户与三个 SSO 应用。Authentik 只允许它的 end-session 路径。
export const PLATFORM_HOSTS = new Set([
  'apps.qyunsgen.com',
  'watch.qyunsgen.com',
  'weknora.qyunsgen.com',
  'translate.qyunsgen.com',
]);
export const AUTHENTIK_HOST = 'auth.qyunsgen.com';
const END_SESSION_PATH = /^\/application\/o\/[a-z0-9-]+\/end-session\/$/;

export const LOGOUT_PATH = '/next/qyuns-logout';
export const DEFAULT_END_SESSION_URL = 'https://auth.qyunsgen.com/application/o/qyunslation/end-session/';

/** 校验 next：站内路径、平台主机的 https 地址、Authentik 的 end-session 页。其余一律拒绝。 */
export function checkNext(next, origin) {
  if (next.length > 2048 || /[\u0000-\u001f\u007f\\]/.test(next)) return { ok: false, reason: 'invalid-characters' };
  if (next.startsWith('//')) return { ok: false, reason: 'protocol-relative' };
  if (next.startsWith('/')) {
    let decoded;
    try { decoded = decodeURIComponent(next); } catch { return { ok: false, reason: 'bad-encoding' }; }
    if (decoded.startsWith('//') || decoded.includes('\\') || /[\u0000-\u001f\u007f]/.test(decoded)) return { ok: false, reason: 'encoded-bypass' };
    return { ok: true, url: new URL(next, origin).toString() };
  }
  let u;
  try { u = new URL(next); } catch { return { ok: false, reason: 'not-a-url' }; }
  if (u.protocol !== 'https:' || u.username || u.password || u.port) return { ok: false, reason: 'scheme-or-userinfo' };
  if (PLATFORM_HOSTS.has(u.hostname)) return { ok: true, url: u.toString() };
  if (u.hostname === AUTHENTIK_HOST && END_SESSION_PATH.test(u.pathname)) return { ok: true, url: u.toString() };
  return { ok: false, reason: 'host-not-allowed' };
}

export function resolveLogoutTarget(next, origin, endSessionUrl = DEFAULT_END_SESSION_URL) {
  if (next === undefined || next === null || next === '') return { ok: true, url: endSessionUrl };
  if (typeof next !== 'string') return { ok: false, reason: 'not-a-string' };
  return checkNext(next, origin);
}

/** CSRF 令牌：与 next/api.js 的读取方式一致（cookie qyunslation_csrf）。 */
export function readCsrf(cookieString) {
  const entry = (cookieString || '').split(';').map((s) => s.trim()).find((s) => s.startsWith('qyunslation_csrf='));
  return entry ? decodeURIComponent(entry.slice('qyunslation_csrf='.length)) : '';
}

/**
 * 执行退出：POST /auth/logout（保持原有 CSRF 校验与 WebSession 撤销）→ 整页跳转。
 * next 无效 → 什么都不做，返回 { rejected: true }。后端不可达也要跳转（本地 cookie 由后端清；不可达时用户至少离开本应用）。
 */
export async function runQyunsLogout({ next, origin, cookie, fetchFn, replace, endSessionUrl }) {
  const target = resolveLogoutTarget(next, origin, endSessionUrl);
  if (!target.ok) return { rejected: true, reason: target.reason };
  try {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 3000);
    await fetchFn('/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': readCsrf(cookie) },
      signal: ctl.signal,
    }).finally(() => clearTimeout(timer));
  } catch {
    // 后端不可达：仍然继续跳转
  }
  replace(target.url);
  return { rejected: false, target: target.url };
}

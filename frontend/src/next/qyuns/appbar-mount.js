// 把 QyunsApps 统一顶栏挂到 /next 页面最上方（PLAN-077 T2）。顶栏脚本是 QyunsApps 生成、复制进 public/ 的同源文件，不手改。
// 只在平台主机上、且已登录时挂载；本地开发、预览、登录页、旧版页面都不动。

const PLATFORM_HOSTS = new Set(['translate.qyunsgen.com']);
const BODY_CLASS = 'qyuns-appbar-on';
const PORTAL = 'https://apps.qyunsgen.com/';

/** 纯函数：要不要显示顶栏。 */
export function shouldShowAppbar({ hostname, authenticated, isPreview, disabled }) {
  return !disabled && authenticated && !isPreview && PLATFORM_HOSTS.has(hostname);
}

// 与 public/qyuns-appbar.js 头部的 QyunsApps@<sha> 保持一致。/app-assets/ 静态资源被边缘设为 1 年 immutable，
// 旧版本（修复前菜单被 contain:content 裁切）会被浏览器长期缓存，靠版本参数换一个新 URL 来绕过。
export const APPBAR_VERSION = '069eab1fc531';

/** vite 的 base 是 /app-assets/，public/ 下的文件构建后位于 /app-assets/qyuns-appbar.js。 */
export function appbarScriptUrl(base = '/') {
  return `${base.endsWith('/') ? base : `${base}/`}qyuns-appbar.js?v=${APPBAR_VERSION}`;
}

export function displayName(user) {
  return String(user?.display_name || user?.name || user?.email || '');
}

let scriptRequested = false;

function remove() {
  document.querySelector('qyuns-appbar')?.remove();
  document.body.classList.remove(BODY_CLASS);
}

/** session: { authenticated, isPreview, user }。幂等，可在每次路由切换后调用。 */
export function syncAppbar(session, env = {}) {
  const show = shouldShowAppbar({
    hostname: env.hostname ?? window.location.hostname, // env.hostname 仅供测试覆盖
    authenticated: Boolean(session?.authenticated),
    isPreview: Boolean(session?.isPreview),
    disabled: env.VITE_QYUNSAPPS_APPBAR === 'false',
  });
  if (!show) return remove();
  const src = appbarScriptUrl(env.BASE_URL || '/');
  if (!scriptRequested && !document.querySelector(`script[src="${src}"]`)) {
    scriptRequested = true;
    const s = document.createElement('script');
    s.src = src;
    s.defer = true;
    document.head.appendChild(s);
  }
  let bar = document.querySelector('qyuns-appbar');
  if (!bar) {
    bar = document.createElement('qyuns-appbar');
    document.body.insertBefore(bar, document.body.firstChild);
  }
  bar.setAttribute('current-app', 'translate');
  bar.setAttribute('portal-href', PORTAL);
  bar.setAttribute('logout-href', '/next/qyuns-logout');
  bar.setAttribute('theme', 'light'); // /next 工作台目前只有亮色
  const name = displayName(session.user);
  if (name) bar.setAttribute('user-name', name);
  else bar.removeAttribute('user-name');
  document.body.classList.add(BODY_CLASS);
}

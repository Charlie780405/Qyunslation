// QyunsApps 接入的唯一入口（PLAN-077 T2）：main.js 里只多几行——import 本文件，并在创建应用之前调用 installQyuns(router)；
// 返回 true 表示这次请求是 /next/qyuns-logout，已由本模块处理，main.js 不应再启动应用。
import '../vendor/tokens.css';
import './qyuns.css';
import { syncAppbar } from './appbar-mount.js';
import { LOGOUT_PATH, runQyunsLogout } from './logout.js';
import { useSessionStore } from '../stores/session.js';

function showRejected() {
  const el = document.createElement('main');
  el.setAttribute('role', 'alert');
  el.style.cssText = 'font:16px/1.6 system-ui,sans-serif;padding:48px 24px;text-align:center';
  el.append('退出链接无效，没有执行退出。');
  const a = document.createElement('a');
  a.href = '/next/workbench';
  a.textContent = '返回工作台';
  a.style.marginLeft = '8px';
  el.append(a);
  document.body.replaceChildren(el);
}

export function installQyuns(router) {
  if (window.location.pathname === LOGOUT_PATH) {
    const next = new URLSearchParams(window.location.search).get('next');
    runQyunsLogout({
      next,
      origin: window.location.origin,
      cookie: document.cookie,
      fetchFn: window.fetch.bind(window),
      replace: (url) => window.location.replace(url),
      endSessionUrl: import.meta.env.VITE_QYUNSAPPS_END_SESSION_URL || undefined,
    }).then((r) => { if (r.rejected) showRejected(); });
    return true;
  }
  router.afterEach(() => {
    const s = useSessionStore();
    syncAppbar({ authenticated: s.isAuthenticated, isPreview: s.isPreview, user: s.user }, import.meta.env);
  });
  return false;
}

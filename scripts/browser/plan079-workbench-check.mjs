// SPDX-License-Identifier: MPL-2.0
// PLAN-079 F8：在真实浏览器（Chromium、WebKit）里验证上传页的拖放，以及空闲/执行中的轮询请求数。
// 加载 `vite build` 的产物，拦截 /api/v1，不访问任何真实服务。环境变量同 plan079-locate-check.mjs
// （QY_BUILD_DIR、QY_PLAYWRIGHT_DIR、可选 QY_WEBKIT_EXEC、QY_OUT_DIR；不需要 PDF）。
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const need = (name) => { if (!process.env[name]) { console.error(`missing env ${name}`); process.exit(3); } return process.env[name]; };
const require = createRequire(`${need('QY_PLAYWRIGHT_DIR').replace(/\/$/, '')}/node_modules/`);
const { chromium, webkit } = require('playwright');
const BUILD = need('QY_BUILD_DIR');
const OUT = process.env.QY_OUT_DIR || BUILD;
const MIME = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

const RUNNING = {
  id: 'r1', filename: 'a.pdf', display_name: 'a.pdf', status: 'translating', stage: 'text', progress: 40, quality_state: 'draft',
  lifecycle: 'executing', generation: 1, direction: 'English → 简体中文', allowed_actions: ['open', 'cancel'], pending_counts: {}, qa_summary: {}, formal_gate: { passed: false, reasons: [] },
};

function startServer(state) {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (code, body, type = 'application/json') => { res.writeHead(code, { 'content-type': type }); res.end(body); };
    if (url.pathname.startsWith('/app-assets/')) {
      const file = path.join(BUILD, url.pathname.slice('/app-assets/'.length));
      if (fs.existsSync(file) && fs.statSync(file).isFile()) return send(200, fs.readFileSync(file), MIME[path.extname(file)] || 'application/octet-stream');
      return send(404, '');
    }
    if (url.pathname.startsWith('/next')) return send(200, fs.readFileSync(`${BUILD}/index.html`), 'text/html');
    if (url.pathname.startsWith('/api/v1')) state.apiRequests.push(`${req.method} ${url.pathname}`);
    const p = url.pathname;
    if (p === '/api/v1/me') return send(200, JSON.stringify({ display_name: 'tester', sub: 'u1', tenant_slug: 'pilot', role: 'translator', capabilities: { workbench_v2: true } }));
    if (p === '/api/v1/translation-runs') return send(200, JSON.stringify({ items: state.runs, total: state.runs.length, next_cursor: null }));
    if (p.endsWith('/events')) return send(200, JSON.stringify({ items: [], next_sequence: 0 }));
    if (p === '/api/v1/preflights') return send(200, JSON.stringify({ items: [], latest: null }));
    if (p === '/api/v1/preferences') return send(200, JSON.stringify({ preferences: {} }));
    if (p === '/api/v1/settings/schema') return send(200, JSON.stringify({ upload: { allowed_extensions: ['.pdf', '.docx'], max_bytes: 1000 } }));
    if (p === '/api/v1/model-profiles') return send(200, JSON.stringify({ items: [] }));
    return send(200, '{}');
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: Boolean(ok), detail }); if (!ok) console.log(`  FAIL ${name} ${detail}`); };

async function open(browserType, browserName, state, { clock = false } = {}) {
  const server = await startServer(state);
  const launchOpts = browserName === 'webkit' ? (process.env.QY_WEBKIT_EXEC ? { executablePath: process.env.QY_WEBKIT_EXEC } : {}) : {};
  let browser;
  try { browser = await browserType.launch(launchOpts); } catch (error) { server.close(); check(`${browserName}: browser launches`, false, String(error).split('\n')[0].slice(0, 160)); return null; }
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  if (clock) await page.clock.install();
  await page.goto(`http://127.0.0.1:${server.address().port}/next/workbench`, { waitUntil: 'networkidle' });
  await page.waitForSelector('.qy-dropzone', { timeout: 15000 });
  await page.waitForTimeout(500);
  return { page, errors, close: async () => { await browser.close(); server.close(); } };
}

// A drag/drop with real DataTransfer files, as the browser would deliver it.
async function dispatchFile(page, selector, type, name, bytes) {
  return page.evaluate(({ selector, type, name, bytes }) => {
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array(bytes)], name));
    const target = document.querySelector(selector);
    target.dispatchEvent(new DragEvent(type, { dataTransfer: dt, bubbles: true, cancelable: true }));
    return { prevented: false };
  }, { selector, type, name, bytes });
}

async function dragAndDrop(browserType, browserName) {
  const state = { runs: [], apiRequests: [] };
  const ctx = await open(browserType, browserName, state);
  if (!ctx) return;
  const { page, errors } = ctx;
  const tag = `${browserName}/drag-drop`;
  try {
    await dispatchFile(page, '.qy-dropzone', 'dragenter', 'a.pdf', 10);
    check(`${tag}: zone highlights while a file is dragged over`, await page.locator('.qy-dropzone.is-dragging').count() === 1);
    await dispatchFile(page, '.qy-dropzone', 'drop', 'a.pdf', 10);
    check(`${tag}: a supported file is selected`, (await page.locator('.qy-dropzone strong').textContent()).includes('a.pdf') && await page.locator('.qy-dropzone.is-dragging').count() === 0);

    await dispatchFile(page, '.qy-dropzone', 'drop', 'tool.exe', 10);
    check(`${tag}: an unsupported format is refused with the reason`, (await page.locator('.qy-callout').first().textContent()).includes('不支持的文件格式'), await page.locator('.qy-callout').first().textContent());

    await dispatchFile(page, '.qy-dropzone', 'drop', 'big.pdf', 5000);
    check(`${tag}: an oversized file is refused with the reason`, (await page.locator('.qy-callout').first().textContent()).includes('文件太大'), await page.locator('.qy-callout').first().textContent());

    const before = page.url();
    await page.evaluate(() => {
      const dt = new DataTransfer();
      dt.items.add(new File(['x'], 'stray.pdf'));
      document.body.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    });
    await page.waitForTimeout(200);
    check(`${tag}: a file dropped outside the zone does not navigate away`, page.url() === before && await page.locator('.qy-dropzone').count() === 1);
    check(`${tag}: no uncaught page errors`, errors.length === 0, errors.join(' | ').slice(0, 200));
  } catch (error) {
    check(`${tag}: scenario ran`, false, String(error).slice(0, 300));
  } finally { await ctx.close(); }
}

async function polling(browserType, browserName, runs, label, stepMs, steps, limit, minimum = 0) {
  const state = { runs, apiRequests: [] };
  const ctx = await open(browserType, browserName, state, { clock: true });
  if (!ctx) return;
  const tag = `${browserName}/${label}`;
  try {
    state.apiRequests.length = 0;
    for (let i = 0; i < steps; i += 1) {
      await ctx.page.clock.runFor(stepMs);
      await ctx.page.waitForTimeout(25);
    }
    const lists = state.apiRequests.filter((r) => r === 'GET /api/v1/translation-runs').length;
    const total = state.apiRequests.length;
    console.log(`  ${tag}: ${lists} list requests, ${total} api requests in ${(stepMs * steps) / 1000}s`);
    check(`${tag}: ${lists} list requests in ${(stepMs * steps) / 1000}s (limit ${limit})`, lists <= limit, `total api=${total} ${[...new Set(state.apiRequests)].join(', ')}`);
    // Positive control: when something is running the poller must actually fire, or "few requests" proves nothing.
    if (minimum > 0) check(`${tag}: the poller does fire while a task runs (>= ${minimum})`, lists >= minimum, `${lists}`);
  } catch (error) {
    check(`${tag}: scenario ran`, false, String(error).slice(0, 300));
  } finally { await ctx.close(); }
}

for (const [browserName, browserType] of [['chromium', chromium], ['webkit', webkit]]) {
  await dragAndDrop(browserType, browserName);
  // Idle list: no timer at all, so 10 minutes of waiting must cost 0 requests.
  await polling(browserType, browserName, [], 'idle-10-minutes', 10000, 60, 0);
  // Something running and unchanged: 2s -> 5s -> 10s back-off keeps a minute under 10 requests (a fixed 2s timer is 30).
  await polling(browserType, browserName, [RUNNING], 'running-1-minute', 1000, 60, 9, 4);
}
const failed = results.filter((r) => !r.ok);
console.log(`${results.length - failed.length}/${results.length} checks passed`);
fs.writeFileSync(`${OUT}/workbench-results.json`, JSON.stringify(results, null, 2));
process.exit(failed.length ? 1 : 0);

// SPDX-License-Identifier: MPL-2.0
// PLAN-079：批准正式稿 -> 自动跳到完成页（有下载按钮）-> 回到 QA 页（可前往导出 / 生成修订版），在 Chromium 与 WebKit 里走一遍。
// 环境变量同 plan079-workbench-check.mjs（QY_BUILD_DIR、QY_PLAYWRIGHT_DIR、可选 QY_WEBKIT_EXEC、QY_OUT_DIR）。
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

const BASE_RUN = {
  id: 'run-1', filename: 'paper.pdf', display_name: '某某文献', generation: 1, status: 'gated', stage: 'review', quality_state: 'review_ready',
  lifecycle: 'review', next_action: 'review', superseded_by: null, source_language: 'English', target_language: '简体中文',
  allowed_actions: ['open', 'rename', 'archive', 'delete', 'retry', 'revise', 'discard', 'requalify', 'approve', 'request_changes'],
  pending_counts: { qa_blockers: 0, qa_unavailable: 0, unresolved_terms: 0 }, qa_summary: { blocker: 1, open_blocker: 0, waived: 1 },
  formal_gate: { passed: true, reasons: [], qa_blockers: 0, term_gate_mode: 'enforce' }, qa_check: { round_no: 1, status: 'succeeded' }, artifacts: [],
};
const APPROVED = {
  ...BASE_RUN, status: 'succeeded', stage: 'export', quality_state: 'approved', lifecycle: 'completed', next_action: 'download',
  allowed_actions: ['open', 'revise', 'download', 'archive'],
  artifacts: [
    { id: 'a1', filename: 'paper_zh.pdf', size_bytes: 2621440, formal_export: true, kind: 'mono', download_url: '/api/v1/translation-runs/run-1/artifacts/a1' },
    { id: 'a2', filename: 'paper_dual.pdf', size_bytes: 4096, formal_export: true, kind: 'dual', download_url: '/api/v1/translation-runs/run-1/artifacts/a2' },
  ],
};
const ITEM = {
  id: 'i1', category: 'ad', severity: 'blocker', code: 'LITERAL_MISSING_IND', message: 'm', object_id: null, resolved: true, evidence: {},
  title: '原文中的 IND / NCT 编号在译文中缺失或被改写', why: 'w', how: 'h', rule_class: 'C1', status: 'false_positive_confirmed', batchable: false,
  is_current: true, round_id: 'rd1', previous_disposition: false, prior_version_disposition: null, disposition: null, history: [],
  allowed_dispositions: [], remedies: [], location: { anchors: [] },
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
    const p = url.pathname;
    if (p === '/api/v1/me') return send(200, JSON.stringify({ display_name: 'tester', sub: 'u1', tenant_slug: 'pilot', role: 'owner', capabilities: { workbench_v2: true } }));
    if (p === '/api/v1/translation-runs/run-1') return send(200, JSON.stringify(state.approved ? APPROVED : BASE_RUN));
    if (p === '/api/v1/translation-runs/run-1/review-decision' && req.method === 'POST') { state.approved = true; state.decisions += 1; return send(200, '{}'); }
    if (p.endsWith('/qa-items')) return send(200, JSON.stringify({ items: [ITEM] }));
    if (p.endsWith('/events')) return send(200, JSON.stringify({ items: [], next_sequence: 0 }));
    if (p.endsWith('/term-candidates')) return send(200, JSON.stringify({ items: [], total: 0, unresolved: 0, page: 1, page_size: 40, rules: {} }));
    if (p.endsWith('/review-draft')) return send(200, JSON.stringify({ comment: '' }));
    if (p === '/api/v1/preferences') return send(200, JSON.stringify({ preferences: {} }));
    if (p === '/api/v1/model-profiles') return send(200, JSON.stringify({ items: [] }));
    if (p.includes('/preview/')) return send(404, '');
    return send(200, '{}');
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: Boolean(ok), detail }); if (!ok) console.log(`  FAIL ${name} ${detail}`); };

async function run(browserType, browserName, sizeName, viewport) {
  const state = { approved: false, decisions: 0 };
  const server = await startServer(state);
  const launchOpts = browserName === 'webkit' ? (process.env.QY_WEBKIT_EXEC ? { executablePath: process.env.QY_WEBKIT_EXEC } : {}) : {};
  let browser;
  const tag = `${browserName}/${sizeName}`;
  try { browser = await browserType.launch(launchOpts); } catch (error) { server.close(); check(`${tag}: browser launches`, false, String(error).split('\n')[0].slice(0, 160)); return; }
  const page = await (await browser.newContext({ viewport })).newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await page.goto(`${base}/next/workbench/run-1`, { waitUntil: 'networkidle' });
    await page.waitForSelector('[data-action="formal-approve"]', { timeout: 15000 });
    check(`${tag}: no export link before approval`, await page.locator('[data-action="go-export"]').count() === 0);

    await page.locator('[data-action="formal-approve"]').click();
    await page.waitForURL('**/next/workbench/run-1/complete', { timeout: 10000 });
    check(`${tag}: approving leaves the QA page for the completion page`, page.url().endsWith('/next/workbench/run-1/complete'), page.url());
    await page.waitForSelector('[data-complete-title]', { timeout: 10000 });
    check(`${tag}: the completion page says the formal version is ready`, (await page.locator('[data-complete-title]').textContent()).includes('正式稿已生成'));
    const links = await page.locator('[data-complete-download]').evaluateAll((els) => els.map((el) => el.getAttribute('href')));
    check(`${tag}: a download button per formal file`, links.length === 2 && links[0].endsWith('/artifacts/a1'), JSON.stringify(links));
    const visible = await page.locator('[data-complete-download]').first().isVisible();
    check(`${tag}: the download button is visible without scrolling away from the page`, visible);
    if (browserName === 'chromium') await page.screenshot({ path: `${OUT}/complete-${sizeName}.png`, fullPage: false });

    await page.locator('[data-complete-back-to-qa]').click();
    await page.waitForURL('**/next/workbench/run-1', { timeout: 10000 });
    await page.waitForSelector('[data-qa-panel]', { timeout: 10000 });
    check(`${tag}: back on the QA page with the handled problems`, await page.locator('[data-qa-panel]').count() === 1);
    check(`${tag}: the QA page links forward to the export page`, await page.locator('[data-action="go-export"]').count() === 1);
    check(`${tag}: and offers to revise the finished version`, await page.locator('[data-action="revise-approved"]').count() === 1);
    check(`${tag}: approval was sent exactly once`, state.decisions === 1, String(state.decisions));
    check(`${tag}: no uncaught page errors`, errors.length === 0, errors.join(' | ').slice(0, 200));
  } catch (error) {
    check(`${tag}: scenario ran`, false, String(error).slice(0, 300));
  } finally { await browser.close(); server.close(); }
}

for (const [browserName, browserType] of [['chromium', chromium], ['webkit', webkit]]) {
  await run(browserType, browserName, 'desktop', { width: 1280, height: 900 });
  await run(browserType, browserName, 'phone', { width: 390, height: 844 });
}
const failed = results.filter((r) => !r.ok);
console.log(`${results.length - failed.length}/${results.length} checks passed`);
fs.writeFileSync(`${OUT}/complete-results.json`, JSON.stringify(results, null, 2));
process.exit(failed.length ? 1 : 0);

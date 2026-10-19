// SPDX-License-Identifier: MPL-2.0
// PLAN-079 阶段 A：在真实浏览器（Chromium、WebKit）里验证“在对照视图定位”。
// 加载 `vite build` 的产物，拦截 /api/v1 并用生成的多页 PDF 应答，不访问任何真实服务。
//
//   环境变量：
//     QY_BUILD_DIR       vite build 的输出目录（base 为 /app-assets/）           必填
//     QY_PDF_DIR         含 source.pdf、translated5.pdf、translated3.pdf 的目录     必填（scripts/browser/plan079_make_pdfs.py 生成）
//     QY_PLAYWRIGHT_DIR  含 node_modules/playwright 的目录                          必填
//     QY_WEBKIT_EXEC     WebKit 启动器（pw_run.sh）；缺省时让 Playwright 自己找，找不到则该浏览器的检查记为失败
//     QY_OUT_DIR         截图与 results.json 的输出目录（缺省 QY_PDF_DIR）
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const need = (name) => { if (!process.env[name]) { console.error(`missing env ${name}`); process.exit(3); } return process.env[name]; };
const require = createRequire(`${need('QY_PLAYWRIGHT_DIR').replace(/\/$/, '')}/node_modules/`);
const { chromium, webkit } = require('playwright');

const BUILD = need('QY_BUILD_DIR');
const PDFS = need('QY_PDF_DIR');
const OUT = process.env.QY_OUT_DIR || PDFS;
const MIME = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json', '.mjs': 'text/javascript', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

function item(overrides) {
  return {
    id: 'i1', category: 'ad', severity: 'blocker', code: 'AD_NUMBER_DRIFT', message: '保护性数字发生变化',
    object_id: null, resolved: false, evidence: {}, title: '数字、剂量或统计量与原文不一致', why: '数值改变会改变临床含义。',
    how: '对照原文位置核对译文。', rule_class: 'C1', status: 'open', batchable: false, is_current: true, round_id: 'rd1',
    previous_disposition: false, prior_version_disposition: null, disposition: null, history: [], allowed_dispositions: ['report_false_positive'],
    location: { anchors: [{ side: 'source', page: 3, label: '45.2%', excerpt: '…45.2% improved…' }] }, ...overrides,
  };
}
const ITEMS = [
  item({}),
  item({ id: 'i2', code: 'LATIN_RESIDUE', title: '译文中英文残留较多', severity: 'warning', rule_class: 'W', allowed_dispositions: ['acknowledge'],
    location: { anchors: [{ side: 'translated', page: 2, label: '英文残留', excerpt: 'Subjects receiving…' }] } }),
  item({ id: 'i3', code: 'AD_NEGATION_DRIFT', title: '否定含义在译文中丢失', location: { anchors: [{ side: 'translated', page: 4, label: '否定', excerpt: 'no' }] } }),
  item({ id: 'i4', code: 'AD_MODALITY_DRIFT', title: '义务、许可或禁止的语气发生变化', location: { anchors: [{ side: 'source', page: 99, label: 'must', excerpt: 'must' }] } }),
];
const RUN = {
  id: 'run-1', filename: 'a.pdf', display_name: 'a.pdf', status: 'gated', stage: 'qa', quality_state: 'qa_blocked', lifecycle: 'qa_action',
  next_action: 'fix_quality_issues', superseded_by: null, generation: 1,
  allowed_actions: ['open', 'rename', 'archive', 'delete', 'retry', 'revise', 'discard', 'requalify', 'open_qa'],
  pending_counts: { qa_blockers: 3, qa_unavailable: 0, unresolved_terms: 0, unconfirmed_affiliations: 0 },
  qa_summary: { blocker: 3, open_blocker: 3, waived: 0 },
  formal_gate: { passed: false, reasons: ['qa_blockers'], qa_blockers: 3, term_gate_mode: 'legacy' },
  qa_check: { round_no: 1, status: 'succeeded', diff: { baseline: 'previous_round', new: 0, resolved: 0, persisting: 4 }, rule_set_version: 'qa-x' },
};

function startServer(translatedPdf) {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (code, body, type = 'application/json') => { res.writeHead(code, { 'content-type': type }); res.end(body); };
    if (url.pathname.startsWith('/app-assets/')) {
      const file = path.join(BUILD, url.pathname.slice('/app-assets/'.length));
      if (fs.existsSync(file) && fs.statSync(file).isFile()) return send(200, fs.readFileSync(file), MIME[path.extname(file)] || 'application/octet-stream');
      return send(404, '');
    }
    if (url.pathname.startsWith('/next')) return send(200, fs.readFileSync(`${BUILD}/index.html`), 'text/html');
    if (url.pathname.endsWith('/preview/source')) return send(200, fs.readFileSync(`${PDFS}/source.pdf`), 'application/pdf');
    if (url.pathname.endsWith('/preview/translated')) return send(200, fs.readFileSync(`${PDFS}/${translatedPdf}.pdf`), 'application/pdf');
    const p = url.pathname;
    if (p === '/api/v1/me') return send(200, JSON.stringify({ display_name: 'tester', sub: 'u1', tenant_slug: 'pilot', role: 'reviewer', capabilities: { workbench_v2: true } }));
    if (p === '/api/v1/translation-runs/run-1') return send(200, JSON.stringify(RUN));
    if (p.endsWith('/events')) return send(200, JSON.stringify({ items: [], next_sequence: 0 }));
    if (p.endsWith('/qa-items')) return send(200, JSON.stringify({ items: ITEMS }));
    if (p.endsWith('/term-candidates')) return send(200, JSON.stringify({ items: [], total: 0, unresolved: 0, page: 1, page_size: 40, rules: {} }));
    if (p.endsWith('/review-draft')) return send(200, JSON.stringify({ comment: '' }));
    if (p === '/api/v1/preferences') return send(200, JSON.stringify({ preferences: {} }));
    if (p === '/api/v1/model-profiles') return send(200, JSON.stringify({ items: [] }));
    return send(200, '{}');
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

const SIZES = { desktop: { width: 1440, height: 900 }, tablet: { width: 800, height: 900 }, phone: { width: 390, height: 844 } };
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: Boolean(ok), detail }); if (!ok) console.log(`  FAIL ${name} ${detail}`); };

async function inView(page) {
  return page.evaluate(() => {
    const r = document.querySelector('.qy-viewer').getBoundingClientRect();
    return { top: Math.round(r.top), bottom: Math.round(r.bottom), vh: window.innerHeight };
  });
}
async function pagePos(page, side, n) {
  return page.evaluate(({ side, n }) => {
    const scroller = document.querySelector(`[data-side="${side}"] .qy-pane-scroll`);
    const el = document.querySelector(`[data-side="${side}"] .qy-page[data-page="${n}"]`);
    if (!scroller || !el) return null;
    const s = scroller.getBoundingClientRect(); const e = el.getBoundingClientRect();
    return { offset: Math.round(e.top - s.top), visible: scroller.offsetParent !== null && s.height > 0, flash: el.classList.contains('qy-page-flash') };
  }, { side, n });
}
async function locate(page, title) {
  await page.getByText(title, { exact: false }).first().click();
  await page.getByRole('button', { name: /在对照视图定位/ }).first().click();
  await page.waitForTimeout(500);
}
async function note(page) { return (await page.locator('[data-locate-note]').first().textContent().catch(() => '')) || ''; }

async function scenario(browserType, browserName, sizeName, translatedPdf) {
  const server = await startServer(translatedPdf);
  const base = `http://127.0.0.1:${server.address().port}`;
  const launchOpts = browserName === 'webkit' ? (process.env.QY_WEBKIT_EXEC ? { executablePath: process.env.QY_WEBKIT_EXEC } : {}) : {};
  let browser;
  try { browser = await browserType.launch(launchOpts); } catch (error) { server.close(); check(`${browserName}/${sizeName}/${translatedPdf}: browser launches`, false, String(error).split('\n')[0].slice(0, 160)); return; }
  const ctx = await browser.newContext({ viewport: SIZES[sizeName] });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  const tag = `${browserName}/${sizeName}/${translatedPdf}`;
  try {
    await page.goto(`${base}/next/workbench/run-1`, { waitUntil: 'networkidle' });
    await page.waitForSelector('[data-qa-panel]', { timeout: 15000 });
    await page.waitForSelector('.qy-page[data-page="3"]', { state: 'attached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(800);

    // 1) source anchor, page 3
    await locate(page, '数字、剂量或统计量与原文不一致');
    let v = await inView(page);
    check(`${tag}: viewer scrolled into view`, v.top >= -5 && v.top < 140 && v.bottom > 200, JSON.stringify(v));
    check(`${tag}: announces the page`, (await note(page)).includes('已定位到源文第 3 页'), await note(page));
    let pos = await pagePos(page, 'source', 3);
    check(`${tag}: source page 3 is at the top of its canvas`, pos && pos.visible && pos.offset >= -12 && pos.offset < 120, JSON.stringify(pos));
    check(`${tag}: target page highlighted`, pos && pos.flash, JSON.stringify(pos));

    // 2) same page again after the user scrolled away
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(200);
    await page.getByRole('button', { name: /在对照视图定位/ }).first().click();
    await page.waitForTimeout(500);
    v = await inView(page);
    check(`${tag}: second click on the same page responds`, v.top >= -5 && v.top < 140, JSON.stringify(v));

    // 3) translated anchor, page 2: the target side must be the visible one on tablet/phone
    await locate(page, '译文中英文残留较多');
    pos = await pagePos(page, 'translated', 2);
    check(`${tag}: translated page 2 visible and positioned`, pos && pos.visible && pos.offset >= -12 && pos.offset < 120, JSON.stringify(pos));
    if (sizeName !== 'desktop') {
      const sourceVisible = await page.evaluate(() => { const s = document.querySelector('[data-side="source"] .qy-pane-scroll'); return !!s && s.offsetParent !== null; });
      check(`${tag}: other side hidden on ${sizeName}`, !sourceVisible);
    }

    // 4) out of range
    await locate(page, '义务、许可或禁止的语气发生变化');
    check(`${tag}: out-of-range is explained`, (await note(page)).includes('超出源文页数（99 > 5）'), await note(page));

    // 5) page 4 of a 3-page translation
    if (translatedPdf === 'translated3') {
      await locate(page, '否定含义在译文中丢失');
      check(`${tag}: out-of-range on a shorter translation`, (await note(page)).includes('超出译文页数（4 > 3）'), await note(page));
    }
    check(`${tag}: no uncaught page errors`, errors.length === 0, errors.join(' | ').slice(0, 200));
    if (sizeName === 'desktop' && browserName === 'chromium' && translatedPdf === 'translated5') {
      await locate(page, '数字、剂量或统计量与原文不一致');
      await page.screenshot({ path: `${OUT}/locate-${browserName}-${sizeName}.png` });
    }
  } catch (error) {
    check(`${tag}: scenario ran`, false, String(error).slice(0, 300));
  } finally {
    await browser.close();
    server.close();
  }
}

for (const [browserName, browserType] of [['chromium', chromium], ['webkit', webkit]]) {
  for (const sizeName of Object.keys(SIZES)) {
    await scenario(browserType, browserName, sizeName, 'translated5');
  }
  await scenario(browserType, browserName, 'desktop', 'translated3');
}
const failed = results.filter((r) => !r.ok);
console.log(`${results.length - failed.length}/${results.length} checks passed`);
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 2));
process.exit(failed.length ? 1 : 0);

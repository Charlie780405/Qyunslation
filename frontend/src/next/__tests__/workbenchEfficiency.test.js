import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia, setActivePinia } from 'pinia';
import axe from 'axe-core';

const apiMock = vi.hoisted(() => ({
  me: vi.fn(),
  listModelProfiles: vi.fn(async () => ({ profiles: [] })),
  listRuns: vi.fn(async () => ({ items: [] })),
  getRunEvents: vi.fn(async () => ({ items: [], generation: 1 })),
  getPreferences: vi.fn(async () => ({})),
  savePreferences: vi.fn(async () => ({})),
  listPreflights: vi.fn(async () => ({ items: [], latest: null })),
  getSettingsSchema: vi.fn(async () => ({ upload: { allowed_extensions: ['.pdf', '.docx'], max_bytes: 50 * 1024 * 1024 } })),
  uploadPreflightResumable: vi.fn(),
}));
vi.mock('../api.js', () => ({ api: apiMock }));
const hashMock = vi.hoisted(() => ({ sha256Hex: vi.fn(async () => 'a'.repeat(64)) }));
vi.mock('../lib/fileHash.js', () => hashMock);

import WorkbenchPage from '../pages/WorkbenchPage.vue';
import AppShell from '../components/AppShell.vue';
import { useSessionStore } from '../stores/session.js';
import { runList } from '../stores/runs.js';
import { connection, markOffline, markOnline } from '../stores/connection.js';

function run(id, overrides = {}) {
  return {
    id, filename: `${id}.pdf`, display_name: null, name_version: 0, generation: 1, version_count: 1,
    source_language: 'English', target_language: '简体中文',
    status: 'succeeded', stage: 'qa', quality_state: 'approved', progress: null, artifacts: [],
    lifecycle: 'completed', allowed_actions: ['open', 'rename', 'archive'], qa_summary: {}, formal_gate: { passed: true },
    ...overrides,
  };
}
const executing = (id) => run(id, { status: 'translating', lifecycle: 'executing', quality_state: 'draft', progress: 10, allowed_actions: ['open', 'cancel'] });
const page = (items) => ({ items, next_cursor: null, total: items.length, facets: { lifecycle: {}, total: items.length } });

async function mountWorkbench() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.user = { display_name: 'tester', capabilities: { workbench_v2: true } };
  session.state = 'authenticated';
  const router = createRouter({
    history: createMemoryHistory('/next'),
    routes: [
      { path: '/workbench', component: WorkbenchPage },
      { path: '/termbase', component: { template: '<div />' } },
      { path: '/settings', component: { template: '<div />' } },
      { path: '/workbench/:runId', name: 'workbench-run', component: { template: '<div />' }, props: true },
    ],
  });
  router.push('/workbench');
  await router.isReady();
  const wrapper = mount(WorkbenchPage, { attachTo: document.body, global: { plugins: [router, pinia] } });
  await flushPromises();
  return wrapper;
}

async function pickAndCheck(wrapper, file = new File(['%PDF'], 'protocol.pdf')) {
  const input = wrapper.find('#workbench-file');
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true });
  await input.trigger('change');
  await wrapper.find('.qy-panel-actions button').trigger('click');
  await flushPromises();
}

beforeEach(() => {
  runList.reset();
  apiMock.listRuns.mockResolvedValue(page([]));
});

afterEach(() => {
  document.body.innerHTML = '';
  vi.useRealTimers();
  vi.clearAllMocks();
  markOnline();
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
});

describe('pre-check shows what limits the file (f2)', () => {
  const ISSUES = [
    { severity: 'info', code: 'TABLES', message: '检测到 3 个表格。', impact: '表格内的数字和单位会进入质量检查。', action: '无需处理。' },
    { severity: 'warning', code: 'SCANNED_PDF', message: '文件主要由扫描页构成（约 8/10 页没有文字层）。', impact: '需要先做 OCR，耗时明显更长。', action: '尽量提供带文字层的原件。' },
  ];

  it('lists each limit with what it means and what to do, worst first, with the page summary', async () => {
    apiMock.uploadPreflightResumable.mockResolvedValue({
      id: 'pf', state: 'ready', filename: 'scan.pdf', format: 'pdf', size_bytes: 2048,
      manifest_summary: { pages: 10, scanned_pages: 8, tables: 3, images: 2 }, issues: ISSUES,
    });
    const wrapper = await mountWorkbench();
    await pickAndCheck(wrapper);
    const box = wrapper.find('[data-preflight-issues]');
    expect(box.exists()).toBe(true);
    expect(box.find('[data-preflight-summary]').text()).toBe('10 页 · 扫描页约 8 · 表格 3 · 图片 2');
    const codes = box.findAll('[data-issue-code]').map((li) => li.attributes('data-issue-code'));
    expect(codes).toEqual(['SCANNED_PDF', 'TABLES']);
    const scanned = box.find('[data-issue-code="SCANNED_PDF"]').text();
    expect(scanned).toContain('影响：需要先做 OCR');
    expect(scanned).toContain('建议：尽量提供带文字层的原件');
    expect(box.find('[data-preflight-blocked]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('a blocked file says why it cannot start and its start button stays off', async () => {
    apiMock.uploadPreflightResumable.mockResolvedValue({
      id: 'pf', state: 'blocked', filename: 'locked.pdf', format: 'pdf', size_bytes: 2048, manifest_summary: {},
      issues: [{ severity: 'blocker', code: 'PDF_ENCRYPTED', message: '文件有打开密码，系统无法读取内容。', impact: '无法翻译。', action: '请在原软件里去掉密码保护后重新上传。' }],
    });
    const wrapper = await mountWorkbench();
    await pickAndCheck(wrapper);
    expect(wrapper.find('[data-preflight-blocked]').text()).toContain('不能开始翻译');
    expect(wrapper.find('[data-issue-code="PDF_ENCRYPTED"]').text()).toContain('去掉密码保护');
    expect(wrapper.find('.qy-preflight-card .qy-primary-button').attributes('disabled')).toBeDefined();
    expect(wrapper.find('.qy-preflight-card .qy-status-badge').text()).toBe('需要处理');
    wrapper.unmount();
  });

  it('a file with nothing to report shows no limits box', async () => {
    apiMock.uploadPreflightResumable.mockResolvedValue({ id: 'pf', state: 'ready', filename: 'a.pdf', format: 'pdf', size_bytes: 1, manifest_summary: {}, issues: [] });
    const wrapper = await mountWorkbench();
    await pickAndCheck(wrapper);
    expect(wrapper.find('[data-preflight-issues]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('keeps the page free of serious accessibility violations with the limits showing', async () => {
    apiMock.uploadPreflightResumable.mockResolvedValue({
      id: 'pf', state: 'ready', filename: 'scan.pdf', format: 'pdf', size_bytes: 2048, manifest_summary: { pages: 10 }, issues: ISSUES,
    });
    const wrapper = await mountWorkbench();
    await pickAndCheck(wrapper);
    const results = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
    expect(results.violations.filter((v) => ['serious', 'critical'].includes(v.impact)).map((v) => v.id)).toEqual([]);
    wrapper.unmount();
  });
});

describe('formats come from the server (f1)', () => {
  it('uses the server list for the accept attribute and the hint, and turns away anything else', async () => {
    const wrapper = await mountWorkbench();
    expect(wrapper.find('#workbench-file').attributes('accept')).toBe('.pdf,.docx');
    expect(wrapper.find('.qy-dropzone').text()).toContain('PDF、DOCX');
    expect(wrapper.find('.qy-dropzone').text()).toContain('50.0 MB');
    await wrapper.find('.qy-dropzone').trigger('drop', { dataTransfer: { files: [new File(['x'], 'slides.pptx')], types: ['Files'] } });
    await flushPromises();
    expect(wrapper.find('.qy-dropzone').text()).not.toContain('slides.pptx');
    expect(wrapper.text()).toContain('不支持的文件格式“.pptx”');
    wrapper.unmount();
  });

  it('refuses a file over the size limit with the numbers', async () => {
    apiMock.getSettingsSchema.mockResolvedValueOnce({ upload: { allowed_extensions: ['.pdf'], max_bytes: 10 } });
    const wrapper = await mountWorkbench();
    await wrapper.find('.qy-dropzone').trigger('drop', { dataTransfer: { files: [new File(['x'.repeat(2048)], 'big.pdf')], types: ['Files'] } });
    await flushPromises();
    expect(wrapper.text()).toContain('文件太大');
    expect(wrapper.find('.qy-dropzone').text()).not.toContain('big.pdf');
    wrapper.unmount();
  });

  it('still works with the built-in list when the schema cannot be read', async () => {
    apiMock.getSettingsSchema.mockRejectedValueOnce(new Error('down'));
    const wrapper = await mountWorkbench();
    expect(wrapper.find('#workbench-file').attributes('accept')).toContain('.pptx');
    wrapper.unmount();
  });
});

describe('same file again (f7)', () => {
  it('sends the file hash with the upload and says when the earlier pre-check was made', async () => {
    apiMock.uploadPreflightResumable.mockResolvedValue({
      id: 'pf', state: 'ready', reused: true, created_at: '2026-10-18T08:30:00', filename: 'a.pdf', format: 'pdf', size_bytes: 1, manifest_summary: {}, issues: [],
    });
    const wrapper = await mountWorkbench();
    await pickAndCheck(wrapper);
    expect(hashMock.sha256Hex).toHaveBeenCalled();
    expect(apiMock.uploadPreflightResumable.mock.calls[0][4]).toEqual({ expectedSha256: 'a'.repeat(64) });
    expect(wrapper.text()).toContain('已复用 10月18日 08:30 做过的预检');
    wrapper.unmount();
  });

  it('uploads normally when no hash could be computed', async () => {
    hashMock.sha256Hex.mockResolvedValueOnce(null);
    apiMock.uploadPreflightResumable.mockResolvedValue({ id: 'pf', state: 'ready', filename: 'a.pdf', format: 'pdf', size_bytes: 1, manifest_summary: {}, issues: [] });
    const wrapper = await mountWorkbench();
    await pickAndCheck(wrapper);
    expect(apiMock.uploadPreflightResumable.mock.calls[0][4]).toEqual({ expectedSha256: null });
    expect(wrapper.text()).toContain('预检已完成');
    wrapper.unmount();
  });
});

describe('the list polls only while something is executing (f3)', () => {
  it('an idle list is fetched once, not on a timer', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    apiMock.listRuns.mockResolvedValue(page([run('a'), run('b')]));
    const wrapper = await mountWorkbench();
    const initial = apiMock.listRuns.mock.calls.length;
    await vi.advanceTimersByTimeAsync(10 * 60 * 1000);
    expect(apiMock.listRuns.mock.calls.length).toBe(initial);
    wrapper.unmount();
  });

  it('an executing task is polled, with growing gaps while nothing changes', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    apiMock.listRuns.mockResolvedValue(page([executing('live')]));
    const wrapper = await mountWorkbench();
    const initial = apiMock.listRuns.mock.calls.length;
    await vi.advanceTimersByTimeAsync(2000);
    expect(apiMock.listRuns.mock.calls.length).toBe(initial + 1);
    await vi.advanceTimersByTimeAsync(2000); // the first poll differed from "nothing seen"; this one may repeat at 2s
    const afterTwo = apiMock.listRuns.mock.calls.length;
    await vi.advanceTimersByTimeAsync(60000);
    const perMinute = apiMock.listRuns.mock.calls.length - afterTwo;
    expect(perMinute).toBeLessThan(10); // a fixed 2s poll would be 30
    wrapper.unmount();
  });

  it('does not poll while the tab is hidden', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    apiMock.listRuns.mockResolvedValue(page([executing('live')]));
    const wrapper = await mountWorkbench();
    const initial = apiMock.listRuns.mock.calls.length;
    await vi.advanceTimersByTimeAsync(60000);
    expect(apiMock.listRuns.mock.calls.length).toBe(initial);
    wrapper.unmount();
  });

  it('reads events incrementally after the first read', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    apiMock.listRuns.mockResolvedValue(page([executing('live')]));
    apiMock.getRunEvents
      .mockResolvedValueOnce({ items: [{ sequence: 1, stage: 'structure', state: 'completed' }, { sequence: 2, stage: 'text', state: 'running' }], generation: 1 })
      .mockResolvedValue({ items: [], generation: 1 });
    const wrapper = await mountWorkbench();
    await vi.advanceTimersByTimeAsync(2100);
    const afters = apiMock.getRunEvents.mock.calls.map((call) => call[1].after_sequence);
    expect(afters[0]).toBe(0);
    expect(afters.slice(1).every((value) => value === 2)).toBe(true);
    wrapper.unmount();
  });

  it('says so, and keeps what it has, when the events cannot be read', async () => {
    apiMock.listRuns.mockResolvedValue(page([executing('live')]));
    apiMock.getRunEvents.mockRejectedValue(Object.assign(new Error('连接中断，请检查网络；页面会自动重试。'), { network: true }));
    const wrapper = await mountWorkbench();
    expect(wrapper.find('[data-events-error]').text()).toContain('连接中断');
    wrapper.unmount();
  });
});

describe('connection banner (f4)', () => {
  it('shows "connection lost, retrying" while offline and hides it when the server answers again', async () => {
    const wrapper = mount(AppShell, { global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot /></a>' } } } });
    expect(wrapper.find('[data-offline-banner]').exists()).toBe(false);
    markOffline();
    await flushPromises();
    expect(wrapper.find('[data-offline-banner]').text()).toContain('连接中断，正在重试');
    expect(connection.offline.value).toBe(true);
    markOnline();
    await flushPromises();
    expect(wrapper.find('[data-offline-banner]').exists()).toBe(false);
    wrapper.unmount();
  });
});

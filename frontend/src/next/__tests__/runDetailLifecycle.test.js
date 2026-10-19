import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia } from 'pinia';

const apiMock = vi.hoisted(() => ({
  getRun: vi.fn(),
  getRunEvents: vi.fn(),
  getQaItems: vi.fn(),
  postReviewDecision: vi.fn(),
  listRunTermCandidates: vi.fn(),
  listRunAffiliationSegments: vi.fn(),
  getReviewDraft: vi.fn(),
  saveReviewDraft: vi.fn(),
  requalifyRun: vi.fn(),
  cancelRun: vi.fn(),
  resumeRun: vi.fn(),
  retryRun: vi.fn(),
  previewUrl: (id, side) => `/api/v1/translation-runs/${id}/preview/${side}`,
}));
vi.mock('../api.js', () => ({ api: apiMock }));
vi.mock('../lib/pdfjs.js', () => ({
  loadPdfjs: async () => ({
    getDocument: () => ({
      promise: Promise.resolve({
        numPages: 1,
        getPage: async () => ({
          getViewport: ({ scale }) => ({ width: 600 * scale, height: 800 * scale }),
          render: () => ({ promise: Promise.resolve(), cancel() {} }),
        }),
        destroy: async () => {},
      }),
    }),
  }),
}));

import RunDetailPage from '../pages/RunDetailPage.vue';

const QA_ITEMS = [
  { id: 'w1', category: 'integrity', severity: 'warning', code: 'LATIN_RESIDUE', message: '英文残留较多', object_id: null, resolved: false, evidence: {} },
  { id: 'b1', category: 'clinical', severity: 'blocker', code: 'LITERAL_MISSING_IND', message: 'IND 编号缺失', object_id: 'obj-9', resolved: false, evidence: { source_text: 'IND 123456' } },
];

const BLOCKED = {
  id: 'run-1', filename: 'a.pdf', status: 'gated', stage: 'qa', quality_state: 'qa_blocked',
  lifecycle: 'qa_action', next_action: 'fix_quality_issues',
  allowed_actions: ['open', 'rename', 'archive', 'delete', 'retry', 'discard', 'requalify', 'open_qa'],
  pending_counts: { qa_blockers: 1, qa_unavailable: 0, unresolved_terms: 0, unconfirmed_affiliations: 0 },
  qa_summary: { blocker: 1 }, formal_gate: { passed: false, qa_blockers: 1 }, progress: null,
};

async function mountPage(url) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, headers: { get: () => 'application/pdf' },
    arrayBuffer: async () => new ArrayBuffer(8), blob: async () => new Blob(['x']),
  })));
  const router = createRouter({
    history: createMemoryHistory('/next'),
    routes: [
      { path: '/workbench', component: { template: '<div />' } },
      { path: '/termbase', component: { template: '<div />' } },
      { path: '/settings', component: { template: '<div />' } },
      { path: '/workbench/:runId', name: 'workbench-run', component: RunDetailPage, props: true },
    ],
  });
  router.push(url);
  await router.isReady();
  const wrapper = mount(RunDetailPage, { props: { runId: 'run-1' }, attachTo: document.body, global: { plugins: [router, createPinia()] } });
  await flushPromises();
  return { wrapper, router };
}

const buttonByText = (wrapper, text) => wrapper.findAll('button').find((b) => b.text() === text);

beforeEach(() => {
  HTMLCanvasElement.prototype.getContext = () => ({});
  apiMock.getRun.mockResolvedValue(BLOCKED);
  apiMock.getRunEvents.mockResolvedValue({ items: [] });
  apiMock.getQaItems.mockResolvedValue({ items: QA_ITEMS });
  apiMock.getReviewDraft.mockResolvedValue({ comment: '' });
  apiMock.listRunTermCandidates.mockResolvedValue({ items: [], total: 0, unresolved: 0, page: 1, page_size: 40, rules: {} });
  apiMock.listRunAffiliationSegments.mockResolvedValue({ items: [], unconfirmed: 0 });
  apiMock.requalifyRun.mockResolvedValue({});
  apiMock.cancelRun.mockResolvedValue({});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  document.body.innerHTML = '';
});

describe('run detail follows the server lifecycle', () => {
  it('shows plain Chinese state instead of status codes', async () => {
    const { wrapper } = await mountPage('/workbench/run-1');
    const head = wrapper.find('.qy-run-detail-head').text();
    expect(head).toContain('待处理质量问题');
    expect(head).not.toMatch(/gated|qa_blocked|translating|状态 \w+_/);
    expect(head).not.toContain('批准正式产物');
    wrapper.unmount();
  });

  it('shows severities in Chinese in the QA list', async () => {
    const { wrapper } = await mountPage('/workbench/run-1');
    const list = wrapper.find('.qy-qa-list').text();
    expect(list).toContain('阻断');
    expect(list).toContain('警告');
    expect(list).not.toMatch(/\bblocker\b|\bwarning\b/);
    wrapper.unmount();
  });

  it('re-check gives progress, success and failure feedback and can be tried again', async () => {
    let fail = true;
    apiMock.requalifyRun.mockImplementation(async () => {
      if (fail) throw new Error('术语服务暂不可用');
      return {};
    });
    const { wrapper } = await mountPage('/workbench/run-1');
    await buttonByText(wrapper, '重新检查').trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('术语服务暂不可用');
    expect(buttonByText(wrapper, '重新检查').attributes('disabled')).toBeUndefined();
    fail = false;
    await buttonByText(wrapper, '重新检查').trigger('click');
    await flushPromises();
    expect(apiMock.requalifyRun).toHaveBeenCalledTimes(2);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('QA outage is explained as not being a translation problem', async () => {
    apiMock.getRun.mockResolvedValue({
      ...BLOCKED, quality_state: 'qa_unavailable', lifecycle: 'qa_unavailable', next_action: 'retry_qa',
      pending_counts: { qa_blockers: 0, qa_unavailable: 1, unresolved_terms: 0, unconfirmed_affiliations: 0 },
      qa_summary: { blocker: 0, unavailable: 1 },
    });
    const { wrapper } = await mountPage('/workbench/run-1');
    const banner = wrapper.find('.qy-lifecycle-banner');
    expect(banner.exists()).toBe(true);
    expect(banner.text()).toContain('不代表译文有问题');
    expect(banner.text()).toContain('重新检查');
    wrapper.unmount();
  });

  it('a link with tab=qa opens on the first blocking issue', async () => {
    const { wrapper, router } = await mountPage('/workbench/run-1?tab=qa');
    expect(router.currentRoute.value.query.obj).toBe('obj-9');
    expect(wrapper.find('.qy-run-inspector').exists()).toBe(false);
    wrapper.unmount();
  });

  it('abandoning a gated version asks first, then calls cancel', async () => {
    const { wrapper } = await mountPage('/workbench/run-1');
    await buttonByText(wrapper, '放弃本版本').trigger('click');
    await flushPromises();
    expect(document.body.querySelector('[data-confirm-dialog]')).not.toBeNull();
    expect(apiMock.cancelRun).not.toHaveBeenCalled();
    document.body.querySelector('[data-confirm-ok]').click();
    await flushPromises();
    expect(apiMock.cancelRun).toHaveBeenCalledWith('run-1');
    wrapper.unmount();
  });

  it('declining the question leaves the version alone', async () => {
    const { wrapper } = await mountPage('/workbench/run-1');
    await buttonByText(wrapper, '放弃本版本').trigger('click');
    await flushPromises();
    document.body.querySelector('[data-confirm-cancel]').click();
    await flushPromises();
    expect(apiMock.cancelRun).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('request-changes failure is shown instead of being swallowed', async () => {
    apiMock.getRun.mockResolvedValue({
      ...BLOCKED, quality_state: 'review_ready', lifecycle: 'review', formal_gate: { passed: true },
      allowed_actions: ['open', 'approve', 'request_changes', 'reject'],
    });
    apiMock.postReviewDecision.mockRejectedValue(new Error('网络连接失败'));
    const { wrapper } = await mountPage('/workbench/run-1');
    await buttonByText(wrapper, '请求修改').trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('网络连接失败');
    wrapper.unmount();
  });
});

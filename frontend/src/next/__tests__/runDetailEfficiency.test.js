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
  enrichRunTermSuggestions: vi.fn(),
  listRunAffiliationSegments: vi.fn(),
  getReviewDraft: vi.fn(),
  saveReviewDraft: vi.fn(),
  requalifyRun: vi.fn(),
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

// PLAN-078f f3/f4/f6 on the task detail page.

const TERM = {
  id: 'term-1', source_term: 'vitiligo', observed_target: '', suggested_target: null, confirmed_target: null,
  term_type: 'disease', risk: 'normal', status: 'pending', version: 1, occurrence_count: 2,
  source_context: 'patient with vitiligo', extraction_reason: 'deterministic:disease',
};
const termPage = (suggester) => ({ items: [TERM], total: 1, unresolved: 1, page: 1, page_size: 40, rules: {}, suggester });
const INTERNAL = { profile_id: 'term-internal-qwen', label: '内网 Qwen（术语抽取，无外发）', provider: 'ollama', egress_scope: 'none' };
const EXTERNAL = { profile_id: 'term-deepseek-flash', label: 'DeepSeek Flash（脱敏术语）', provider: 'deepseek', egress_scope: 'redacted_term_snippets' };

const COMPLETED = {
  id: 'run-1', filename: 'a.pdf', status: 'succeeded', stage: 'review', quality_state: 'approved', lifecycle: 'completed',
  allowed_actions: ['open'], pending_counts: {}, formal_gate: { passed: true }, progress: null, generation: 1,
};
const EXECUTING = { ...COMPLETED, status: 'translating', stage: 'text', quality_state: 'draft', lifecycle: 'executing', progress: 20 };

async function mountPage() {
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
  router.push('/workbench/run-1');
  await router.isReady();
  const wrapper = mount(RunDetailPage, { props: { runId: 'run-1' }, attachTo: document.body, global: { plugins: [router, createPinia()] } });
  await flushPromises();
  return wrapper;
}

const suggestButton = (wrapper) => wrapper.find('[data-term-suggest]');
const dialog = () => document.body.querySelector('[data-confirm-dialog]');

beforeEach(() => {
  HTMLCanvasElement.prototype.getContext = () => ({});
  apiMock.getRun.mockResolvedValue(COMPLETED);
  apiMock.getRunEvents.mockResolvedValue({ items: [], generation: 1 });
  apiMock.getQaItems.mockResolvedValue({ items: [] });
  apiMock.getReviewDraft.mockResolvedValue({ comment: '' });
  apiMock.saveReviewDraft.mockResolvedValue({});
  apiMock.listRunTermCandidates.mockResolvedValue(termPage(INTERNAL));
  apiMock.listRunAffiliationSegments.mockResolvedValue({ items: [], unconfirmed: 0 });
  apiMock.enrichRunTermSuggestions.mockResolvedValue({ ...termPage(INTERNAL), suggestions_enriched: 1 });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  document.body.innerHTML = '';
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
});

describe('term suggestions are never requested by opening the page (f6)', () => {
  it('does not call the suggestion endpoint on load, even when terms have no suggestion yet', async () => {
    const wrapper = await mountPage();
    expect(apiMock.enrichRunTermSuggestions).not.toHaveBeenCalled();
    expect(suggestButton(wrapper).exists()).toBe(true);
    wrapper.unmount();
  });

  it('says where the snippets go before the click: in-house stays in-house', async () => {
    const wrapper = await mountPage();
    const note = wrapper.find('[data-term-suggest-scope]').text();
    expect(note).toContain('数据不离开内网');
    expect(note).toContain('内网 Qwen');
    wrapper.unmount();
  });

  it('an in-house model runs on the click without asking', async () => {
    const wrapper = await mountPage();
    await suggestButton(wrapper).trigger('click');
    await flushPromises();
    expect(dialog()).toBeNull();
    expect(apiMock.enrichRunTermSuggestions).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it('an external model names the recipient and waits for a yes', async () => {
    apiMock.listRunTermCandidates.mockResolvedValue(termPage(EXTERNAL));
    const wrapper = await mountPage();
    expect(wrapper.find('[data-term-suggest-scope]').text()).toContain('发送给外部服务（DeepSeek Flash');
    await suggestButton(wrapper).trigger('click');
    await flushPromises();
    expect(dialog().textContent).toContain('DeepSeek Flash');
    expect(apiMock.enrichRunTermSuggestions).not.toHaveBeenCalled();
    document.body.querySelector('[data-confirm-ok]').click();
    await flushPromises();
    expect(apiMock.enrichRunTermSuggestions).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it('declining the external send sends nothing', async () => {
    apiMock.listRunTermCandidates.mockResolvedValue(termPage(EXTERNAL));
    const wrapper = await mountPage();
    await suggestButton(wrapper).trigger('click');
    await flushPromises();
    document.body.querySelector('[data-confirm-cancel]').click();
    await flushPromises();
    expect(apiMock.enrichRunTermSuggestions).not.toHaveBeenCalled();
    wrapper.unmount();
  });
});

describe('detail polling (f3)', () => {
  it('a finished task is not polled at all', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const wrapper = await mountPage();
    const calls = apiMock.getRun.mock.calls.length;
    await vi.advanceTimersByTimeAsync(10 * 60 * 1000);
    expect(apiMock.getRun.mock.calls.length).toBe(calls);
    expect(apiMock.getQaItems.mock.calls.length).toBe(1);
    wrapper.unmount();
  });

  it('an executing task polls only the run and new events while nothing changes', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    apiMock.getRun.mockResolvedValue(EXECUTING);
    const wrapper = await mountPage();
    const qaBefore = apiMock.getQaItems.mock.calls.length;
    await vi.advanceTimersByTimeAsync(60000);
    expect(apiMock.getRun.mock.calls.length).toBeGreaterThan(2);
    expect(apiMock.getQaItems.mock.calls.length).toBe(qaBefore); // the heavy lists wait for a change
    expect(apiMock.listRunAffiliationSegments).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('reloads the lists, and stops polling, once the run finishes', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    apiMock.getRun.mockResolvedValue(EXECUTING);
    const wrapper = await mountPage();
    const qaBefore = apiMock.getQaItems.mock.calls.length;
    apiMock.getRun.mockResolvedValue({ ...COMPLETED, status: 'gated', lifecycle: 'qa_action', quality_state: 'qa_blocked' });
    await vi.advanceTimersByTimeAsync(2100);
    expect(apiMock.getQaItems.mock.calls.length).toBeGreaterThan(qaBefore);
    const runCalls = apiMock.getRun.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5 * 60 * 1000);
    expect(apiMock.getRun.mock.calls.length).toBe(runCalls);
    wrapper.unmount();
  });

  it('does not poll while the tab is hidden', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    apiMock.getRun.mockResolvedValue(EXECUTING);
    const wrapper = await mountPage();
    const calls = apiMock.getRun.mock.calls.length;
    await vi.advanceTimersByTimeAsync(60000);
    expect(apiMock.getRun.mock.calls.length).toBe(calls);
    wrapper.unmount();
  });
});

describe('failures are visible, not swallowed (f4)', () => {
  it('a term list that cannot load is reported without hiding the rest of the page', async () => {
    apiMock.listRunTermCandidates.mockRejectedValue(new Error('terms down'));
    const wrapper = await mountPage();
    expect(wrapper.find('[data-soft-issue]').text()).toContain('术语候选没能加载');
    expect(wrapper.find('.qy-run-detail-head').exists()).toBe(true);
    wrapper.unmount();
  });

  it('does not request affiliation review data', async () => {
    const wrapper = await mountPage();
    expect(apiMock.listRunAffiliationSegments).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('says that the review comment is not saved when saving fails', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    apiMock.getRun.mockResolvedValue({ ...COMPLETED, status: 'gated', lifecycle: 'review', quality_state: 'review_ready', allowed_actions: ['open', 'approve', 'request_changes'] });
    apiMock.saveReviewDraft.mockRejectedValue(Object.assign(new Error('x'), { network: true }));
    const wrapper = await mountPage();
    await wrapper.find('.qy-review-comment textarea').setValue('需要核对剂量');
    await vi.advanceTimersByTimeAsync(700);
    await flushPromises();
    expect(wrapper.find('[data-draft-error]').text()).toContain('暂未保存');
    wrapper.unmount();
  });

  it('a failing action shows a message and the button works again', async () => {
    apiMock.getRun.mockResolvedValue({ ...COMPLETED, status: 'gated', lifecycle: 'qa_action', quality_state: 'qa_blocked', allowed_actions: ['open', 'requalify'], pending_counts: { qa_blockers: 1 } });
    apiMock.requalifyRun.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    const wrapper = await mountPage();
    const button = () => wrapper.findAll('button').find((b) => b.text() === '重新检查');
    await button().trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('重新检查失败');
    expect(wrapper.find('[role="alert"]').text()).toContain('稍后重试');
    expect(button().attributes('disabled')).toBeUndefined();
    wrapper.unmount();
  });
});

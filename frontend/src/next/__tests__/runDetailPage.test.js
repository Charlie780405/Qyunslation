import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia } from 'pinia';
import axe from 'axe-core';

const apiMock = vi.hoisted(() => ({
  getRun: vi.fn(),
  getRunEvents: vi.fn(),
  getQaItems: vi.fn(),
  postReviewDecision: vi.fn(),
  retryRun: vi.fn(),
  previewUrl: (id, side) => `/api/v1/translation-runs/${id}/preview/${side}`,
}));
vi.mock('../api.js', () => ({ api: apiMock }));

const fakePage = {
  getViewport: ({ scale }) => ({ width: 600 * scale, height: 800 * scale }),
  render: () => ({ promise: Promise.resolve(), cancel() {} }),
};
vi.mock('../lib/pdfjs.js', () => ({
  loadPdfjs: async () => ({
    getDocument: () => ({
      promise: Promise.resolve({
        numPages: 3,
        getPage: async () => fakePage,
        destroy: async () => {},
      }),
    }),
  }),
}));

import RunDetailPage from '../pages/RunDetailPage.vue';
import DualCanvasViewer from '../components/DualCanvasViewer.vue';

const QA_ITEMS = [
  { id: 'q1', category: 'term', severity: 'blocker', code: 'TERM_DRIFT', message: '药名漂移', object_id: 'obj-1', resolved: false, evidence: { source_text: 'Dupilumab', translation: '度普利尤单抗' } },
  { id: 'q2', category: 'layout', severity: 'warning', code: 'FONT_SMALL', message: '字号偏小', object_id: null, resolved: false, evidence: {} },
];

function pdfResponse(status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/pdf' },
    arrayBuffer: async () => new ArrayBuffer(8),
    blob: async () => new Blob(['x']),
  };
}

async function mountPage(url, { translatedStatus = 200 } = {}) {
  vi.stubGlobal('fetch', vi.fn(async (u) => (
    String(u).endsWith('/translated') ? pdfResponse(translatedStatus) : pdfResponse(200)
  )));
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
  const wrapper = mount(RunDetailPage, {
    props: { runId: 'run-1' },
    attachTo: document.body,
    global: { plugins: [router, createPinia()] },
  });
  await flushPromises();
  return { wrapper, router };
}

beforeEach(() => {
  HTMLCanvasElement.prototype.getContext = () => ({});
  apiMock.getRun.mockResolvedValue({ id: 'run-1', filename: 'a.pdf', status: 'completed', stage: 'review', quality_state: 'review_ready' });
  apiMock.getRunEvents.mockResolvedValue({ items: [{ stage: 'validation', state: 'completed', message: 'ok' }] });
  apiMock.getQaItems.mockResolvedValue({ items: QA_ITEMS });
  apiMock.postReviewDecision.mockResolvedValue({});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  document.body.innerHTML = '';
});

describe('RunDetailPage', () => {
  it('selecting a QA item writes obj to the URL and shows only available fields', async () => {
    const { wrapper, router } = await mountPage('/workbench/run-1');
    const buttons = wrapper.findAll('.qy-qa-item');
    expect(buttons).toHaveLength(2);

    await buttons[0].trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.query.obj).toBe('obj-1');
    expect(wrapper.find('[data-field="source"]').text()).toBe('Dupilumab');
    expect(wrapper.find('[data-field="translation"]').text()).toBe('度普利尤单抗');
    expect(wrapper.find('[data-field="terms"]').text()).toBe('—');
    expect(wrapper.find('[data-field="history"]').text()).toBe('—');

    await buttons[1].trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.query.obj).toBe('qa:q2');
    expect(wrapper.find('[data-field="source"]').text()).toBe('—');
    expect(wrapper.find('[data-field="object_id"]').text()).toBe('—');
    wrapper.unmount();
  });

  it('restores the selected object from the URL', async () => {
    const { wrapper } = await mountPage('/workbench/run-1?obj=obj-1&page=2&zoom=1.5&sync=0');
    expect(wrapper.find('[data-field="source"]').text()).toBe('Dupilumab');
    expect(wrapper.find('input[aria-label="当前页码"]').element.value).toBe('2');
    expect(wrapper.find('.qy-viewer-zoom').text()).toBe('150%');
    expect(wrapper.find('[aria-label="同步滚动"]').attributes('aria-pressed')).toBe('false');
    wrapper.unmount();
  });

  it('keeps the technical log collapsed in an in-flow drawer', async () => {
    const { wrapper } = await mountPage('/workbench/run-1');
    const toggle = wrapper.find('[aria-controls="qy-log-drawer"]');
    expect(toggle.attributes('aria-expanded')).toBe('false');
    expect(wrapper.find('#qy-log-drawer').isVisible()).toBe(false);
    await toggle.trigger('click');
    expect(wrapper.find('#qy-log-drawer').isVisible()).toBe(true);
    wrapper.unmount();
  });

  it('approve and request-changes still call the review API', async () => {
    const { wrapper } = await mountPage('/workbench/run-1');
    await wrapper.findAll('button').find((b) => b.text() === '批准正式产物').trigger('click');
    await wrapper.findAll('button').find((b) => b.text() === '请求修改').trigger('click');
    expect(apiMock.postReviewDecision).toHaveBeenCalledWith('run-1', { decision: 'approve' });
    expect(apiMock.postReviewDecision).toHaveBeenCalledWith('run-1', { decision: 'request_changes' });
    wrapper.unmount();
  });

  it('shows the not-yet-generated empty state when translated preview is 409', async () => {
    const { wrapper } = await mountPage('/workbench/run-1', { translatedStatus: 409 });
    const translated = wrapper.find('[data-side="translated"]');
    expect(translated.text()).toContain('译文预览尚未生成');
    expect(wrapper.find('[data-side="source"]').text()).not.toContain('译文预览尚未生成');
    wrapper.unmount();
  });

  it('has no serious or critical axe violations in the page shell', async () => {
    const { wrapper } = await mountPage('/workbench/run-1?obj=obj-1');
    const results = await axe.run(wrapper.element, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    const severe = results.violations.filter((v) => ['serious', 'critical'].includes(v.impact));
    expect(severe.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(' | ')}`)).toEqual([]);
    wrapper.unmount();
  });
});

describe('DualCanvasViewer', () => {
  it('renders two panes on desktop and one at a time with a toggle on phones', async () => {
    const mm = (matches) => (query) => ({
      matches: matches(query), media: query, addEventListener() {}, removeEventListener() {},
    });
    vi.stubGlobal('fetch', vi.fn(async () => pdfResponse(200)));
    window.matchMedia = mm((q) => q.includes('1024'));
    let wrapper = mount(DualCanvasViewer, { props: { runId: 'r' }, attachTo: document.body });
    await flushPromises();
    expect(wrapper.attributes('data-layout')).toBe('desktop');
    expect(wrapper.findAll('.qy-viewer-slot').filter((s) => s.isVisible())).toHaveLength(2);
    expect(wrapper.findAll('canvas').length).toBeGreaterThan(0);
    wrapper.unmount();

    window.matchMedia = mm(() => false);
    wrapper = mount(DualCanvasViewer, { props: { runId: 'r' }, attachTo: document.body });
    await flushPromises();
    expect(wrapper.attributes('data-layout')).toBe('phone');
    expect(wrapper.findAll('.qy-viewer-slot').filter((s) => s.isVisible())).toHaveLength(1);
    await wrapper.find('[aria-label="显示译文"]').trigger('click');
    expect(wrapper.find('#qy-panel-translated').isVisible()).toBe(true);
    expect(wrapper.find('#qy-panel-source').isVisible()).toBe(false);
    wrapper.unmount();
    delete window.matchMedia;
  });

  it('emits page and zoom updates from the controls', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => pdfResponse(200)));
    const wrapper = mount(DualCanvasViewer, { props: { runId: 'r', page: 1, zoom: 1 }, attachTo: document.body });
    await flushPromises();
    await wrapper.find('[aria-label="下一页"]').trigger('click');
    expect(wrapper.emitted('update:page').at(-1)).toEqual([2]);
    await wrapper.find('[aria-label="放大"]').trigger('click');
    expect(wrapper.emitted('update:zoom').at(-1)).toEqual([1.25]);
    await wrapper.find('[aria-label="适应宽度"]').trigger('click');
    expect(wrapper.emitted('update:zoom').at(-1)).toEqual(['fit']);
    wrapper.unmount();
  });
});

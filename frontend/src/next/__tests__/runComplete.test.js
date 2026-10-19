import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia } from 'pinia';

const apiMock = vi.hoisted(() => ({
  getRun: vi.fn(),
  previewUrl: (id, side) => `/api/v1/translation-runs/${id}/preview/${side}`,
}));
vi.mock('../api.js', () => ({ api: apiMock }));

import RunCompletePage from '../pages/RunCompletePage.vue';

const APPROVED = {
  id: 'run-9', filename: 'paper.pdf', display_name: '某某文献', generation: 2, quality_state: 'approved', status: 'succeeded',
  source_language: 'English', target_language: '简体中文',
  artifacts: [
    { id: 'a1', filename: 'paper_zh.pdf', size_bytes: 2_621_440, formal_export: true, kind: 'mono', download_url: '/api/v1/translation-runs/run-9/artifacts/a1' },
    { id: 'a2', filename: 'paper_dual.pdf', size_bytes: 4096, formal_export: true, kind: 'dual', download_url: '/api/v1/translation-runs/run-9/artifacts/a2' },
    { id: 'a3', filename: 'draft.pdf', size_bytes: 10, formal_export: false, kind: 'draft', download_url: '/api/v1/translation-runs/run-9/artifacts/a3' },
  ],
};

async function mountComplete(run) {
  apiMock.getRun.mockResolvedValue(run);
  const router = createRouter({
    history: createMemoryHistory('/next'),
    routes: [
      { path: '/workbench', component: { template: '<div />' } },
      { path: '/workbench/:runId', component: { template: '<div />' } },
      { path: '/workbench/:runId/complete', component: RunCompletePage, props: true },
      { path: '/termbase', component: { template: '<div />' } },
      { path: '/settings', component: { template: '<div />' } },
    ],
  });
  router.push('/workbench/run-9/complete');
  await router.isReady();
  const wrapper = mount(RunCompletePage, { props: { runId: 'run-9' }, attachTo: document.body, global: { plugins: [router, createPinia()] } });
  await flushPromises();
  return { wrapper, router };
}

afterEach(() => {
  vi.clearAllMocks();
  document.body.innerHTML = '';
});

describe('run completion page', () => {
  it('shows the formal files with a download button each, and nothing that is not formal', async () => {
    const { wrapper } = await mountComplete(APPROVED);
    expect(wrapper.find('[data-complete-title]').text()).toBe('正式稿已生成');
    const files = wrapper.findAll('[data-complete-file]');
    expect(files.map((f) => f.find('strong').text())).toEqual(['paper_zh.pdf', 'paper_dual.pdf']);
    expect(files[0].text()).toContain('2.5 MB');
    expect(files[0].find('[data-complete-download]').attributes('href')).toBe('/api/v1/translation-runs/run-9/artifacts/a1');
    expect(wrapper.text()).not.toContain('draft.pdf');
    wrapper.unmount();
  });

  it('leads back to the QA page and says the delivered version is kept', async () => {
    const { wrapper } = await mountComplete(APPROVED);
    const back = wrapper.find('[data-complete-back-to-qa]');
    expect(back.attributes('href')).toBe('/next/workbench/run-9');
    expect(wrapper.text()).toContain('当前这一版的正式稿会保留');
    wrapper.unmount();
  });

  it('offers no downloads for a version that is not approved yet', async () => {
    const { wrapper } = await mountComplete({ ...APPROVED, quality_state: 'review_ready', status: 'gated' });
    expect(wrapper.find('[data-complete-title]').text()).toContain('还没有批准');
    expect(wrapper.find('[data-complete-download]').exists()).toBe(false);
    expect(wrapper.find('[data-complete-back-to-qa]').exists()).toBe(true);
    wrapper.unmount();
  });

  it('says so when an approved run has no exportable file yet', async () => {
    const { wrapper } = await mountComplete({ ...APPROVED, artifacts: [] });
    expect(wrapper.find('[data-complete-no-files]').exists()).toBe(true);
    wrapper.unmount();
  });
});

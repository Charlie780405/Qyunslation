import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia, setActivePinia } from 'pinia';

const apiMock = vi.hoisted(() => ({
  listTerms: vi.fn(),
  listLanguageAssetReleases: vi.fn(),
  listStyleProfiles: vi.fn(),
  listQualityRules: vi.fn(),
  previewLanguageAssetImport: vi.fn(),
  applyLanguageAssetImport: vi.fn(),
  createConcept: vi.fn(),
}));
vi.mock('../api.js', () => ({ api: apiMock }));

import TermbasePage from '../pages/TermbasePage.vue';
import { useSessionStore } from '../stores/session.js';

async function mountTermbase(capabilities = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.user = { display_name: 'tester', capabilities: { workbench_v2: true, ...capabilities } };
  session.state = 'authenticated';
  const router = createRouter({
    history: createMemoryHistory('/next'),
    routes: [{ path: '/termbase', component: TermbasePage }],
  });
  await router.push('/termbase');
  await router.isReady();
  const wrapper = mount(TermbasePage, { attachTo: document.body, global: { plugins: [router, pinia] } });
  await flushPromises();
  return wrapper;
}

afterEach(() => {
  vi.clearAllMocks();
  document.body.innerHTML = '';
});

function primeApi() {
  apiMock.listTerms.mockResolvedValue([]);
  apiMock.listLanguageAssetReleases.mockResolvedValue({ items: [] });
  apiMock.listStyleProfiles.mockResolvedValue({ items: [] });
  apiMock.listQualityRules.mockResolvedValue({ items: [] });
}

describe('termbase permissions', () => {
  it('locks import and create actions for users without term administration capability', async () => {
    primeApi();
    const wrapper = await mountTermbase();
    const importButton = wrapper.find('[data-term-action="import"]');
    const createButton = wrapper.find('[data-term-action="create"]');
    expect(importButton.attributes('aria-disabled')).toBe('true');
    expect(createButton.attributes('aria-disabled')).toBe('true');
    expect(importButton.classes()).toContain('is-locked');
    expect(createButton.classes()).toContain('is-locked');
    await importButton.trigger('click');
    expect(wrapper.find('[data-term-permission-notice]').text()).toContain('请联系术语管理员');
    expect(wrapper.find('.qy-import-callout').exists()).toBe(false);
    wrapper.unmount();
  });

  it('opens import and new-term workflows for a term administrator', async () => {
    primeApi();
    apiMock.createConcept.mockResolvedValue({ id: 'concept-1', status: 'staging' });
    const wrapper = await mountTermbase({ can_manage_terms: true });
    await wrapper.find('[data-term-action="import"]').trigger('click');
    expect(wrapper.find('.qy-import-callout').exists()).toBe(true);
    await wrapper.find('[data-term-action="create"]').trigger('click');
    expect(wrapper.find('[data-new-term-form]').exists()).toBe(true);
    const fields = wrapper.findAll('[data-new-term-form] input');
    await fields[0].setValue('primary endpoint');
    await fields[1].setValue('主要终点');
    await fields[2].setValue('clinical');
    await wrapper.find('[data-new-term-form] form').trigger('submit');
    await flushPromises();
    expect(apiMock.createConcept).toHaveBeenCalledWith(expect.objectContaining({
      preferred_source: 'primary endpoint',
      preferred_target: '主要终点',
      domain: 'clinical',
      term_type: 'general',
    }));
    expect(wrapper.find('[data-new-term-form]').exists()).toBe(false);
    wrapper.unmount();
  });
});

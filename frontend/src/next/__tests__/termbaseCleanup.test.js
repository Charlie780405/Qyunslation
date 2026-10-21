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
  updateConcept: vi.fn(),
  batchConceptStatus: vi.fn(),
}));
const confirmMock = vi.hoisted(() => ({ confirmDialog: vi.fn() }));
vi.mock('../api.js', () => ({ api: apiMock }));
vi.mock('../lib/confirm.js', async (importOriginal) => ({ ...(await importOriginal()), confirmDialog: confirmMock.confirmDialog }));

import TermbasePage from '../pages/TermbasePage.vue';
import { useSessionStore } from '../stores/session.js';

function concept(id, source, target, extra = {}) {
  const terms = [{ lang: 'en', text: source, role: 'preferred' }];
  if (target) terms.push({ lang: 'zh', text: target, role: 'preferred' });
  return {
    id,
    status: 'curated',
    layer: 'clinical',
    domain: 'clinical',
    term_type: 'general',
    target_state: target ? 'translated' : 'missing',
    compliance: null,
    forbiddens: [],
    terms,
    ...extra,
  };
}

const ROWS = [
  concept('a', 'sparse sampling', '稀疏采样', { layer: 'org', compliance: { code: 'GENERIC_PHRASE', label: '泛用短语' } }),
  concept('b', 'GSK', '', { layer: 'org', domain: 'org', target_state: 'keep_source', do_not_translate: true }),
  concept('c', 'NewCo', '', { layer: 'org', domain: 'org' }),
  concept('d', 'old term', '旧词', { status: 'rejected' }),
  concept('e', 'pending term', '待审词', { status: 'staging' }),
];

async function mountTermbase(capabilities = { can_manage_terms: true }) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.user = { display_name: 'tester', capabilities: { workbench_v2: true, ...capabilities } };
  session.state = 'authenticated';
  const router = createRouter({ history: createMemoryHistory('/next'), routes: [{ path: '/termbase', component: TermbasePage }] });
  await router.push('/termbase');
  await router.isReady();
  const wrapper = mount(TermbasePage, { attachTo: document.body, global: { plugins: [router, pinia] } });
  await flushPromises();
  return wrapper;
}

function prime(rows = ROWS) {
  apiMock.listTerms.mockResolvedValue(rows);
  apiMock.listLanguageAssetReleases.mockResolvedValue({ items: [] });
  apiMock.listStyleProfiles.mockResolvedValue({ items: [] });
  apiMock.listQualityRules.mockResolvedValue({ items: [] });
  apiMock.updateConcept.mockResolvedValue({});
  apiMock.batchConceptStatus.mockResolvedValue({ changed: ['a'], skipped: [] });
}

afterEach(() => {
  vi.clearAllMocks();
  document.body.innerHTML = '';
});

const viewButton = (wrapper, key) => wrapper.find(`[data-term-view="${key}"]`);

describe('termbase page: complete list, scrolling and counts', () => {
  it('requests the full list and keeps the table in its own scroll region', async () => {
    prime();
    const wrapper = await mountTermbase();
    expect(apiMock.listTerms).toHaveBeenCalledWith({ limit: 2000 });
    const region = wrapper.find('[data-term-scroll]');
    expect(region.exists()).toBe(true);
    expect(region.attributes('tabindex')).toBe('0');
    expect(region.attributes('role')).toBe('region');
    wrapper.unmount();
  });

  it('shows real counts per view instead of zeros, and separates rejected terms', async () => {
    prime();
    const wrapper = await mountTermbase();
    expect(viewButton(wrapper, 'company').text()).toContain('3');
    expect(viewButton(wrapper, 'pending').text()).toContain('1');
    expect(viewButton(wrapper, 'suspect').text()).toContain('1');
    expect(viewButton(wrapper, 'rejected').text()).toContain('1');
    expect(wrapper.text()).toContain('术语库 4');
    expect(wrapper.find('[data-term-count]').text()).toContain('共 5 条');
    await viewButton(wrapper, 'rejected').trigger('click');
    expect(wrapper.findAll('[data-term-row]')).toHaveLength(1);
    wrapper.unmount();
  });
});

describe('termbase page: filter button', () => {
  it('opens a filter panel, narrows the list and can reset', async () => {
    prime();
    const wrapper = await mountTermbase();
    const toggle = wrapper.find('[data-term-filter-toggle]');
    expect(toggle.attributes('aria-expanded')).toBe('false');
    await toggle.trigger('click');
    expect(toggle.attributes('aria-expanded')).toBe('true');
    expect(wrapper.find('[data-term-filter-panel]').exists()).toBe(true);
    const state = wrapper.find('select[aria-label="按译名状态筛选"]');
    await state.setValue('missing');
    expect(wrapper.findAll('[data-term-row]')).toHaveLength(1);
    expect(wrapper.find('[data-term-filter-count]').text()).toBe('1');
    await wrapper.find('[data-term-filter-reset]').trigger('click');
    expect(wrapper.findAll('[data-term-row]')).toHaveLength(3);
    wrapper.unmount();
  });
});

describe('termbase page: pending translations', () => {
  it('labels do-not-translate terms as keep-source and offers a fill entry for truly missing ones', async () => {
    prime();
    const wrapper = await mountTermbase();
    expect(wrapper.findAll('[data-target-keep]')).toHaveLength(1);
    expect(wrapper.findAll('[data-target-missing]')).toHaveLength(1);
    await wrapper.find('[data-term-fill]').trigger('click');
    await flushPromises();
    const input = wrapper.find('[data-term-target-input]');
    expect(input.exists()).toBe(true);
    await input.setValue('新公司');
    await wrapper.find('[data-term-edit]').trigger('submit');
    await flushPromises();
    expect(apiMock.updateConcept).toHaveBeenCalledWith('c', { preferred_target: '新公司' });
    expect(apiMock.listTerms).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it('does not offer editing to users without term administration capability', async () => {
    prime();
    const wrapper = await mountTermbase({});
    expect(wrapper.find('[data-term-fill]').exists()).toBe(false);
    expect(wrapper.find('[data-term-select-all]').exists()).toBe(false);
    wrapper.unmount();
  });
});

describe('termbase page: cleanup', () => {
  it('rejects the selected suspected terms after confirmation', async () => {
    prime();
    confirmMock.confirmDialog.mockResolvedValue(true);
    const wrapper = await mountTermbase();
    await viewButton(wrapper, 'suspect').trigger('click');
    await wrapper.find('[data-term-select-all]').setValue(true);
    expect(wrapper.find('[data-term-bulkbar]').text()).toContain('已选 1 条');
    await wrapper.find('[data-term-bulk-reject]').trigger('click');
    await flushPromises();
    expect(confirmMock.confirmDialog).toHaveBeenCalledWith(expect.objectContaining({ danger: true }));
    expect(apiMock.batchConceptStatus).toHaveBeenCalledWith({ ids: ['a'], status: 'rejected' });
    expect(wrapper.find('[data-term-action-notice]').text()).toContain('已驳回 1 条');
    wrapper.unmount();
  });

  it('does nothing when the confirmation is cancelled', async () => {
    prime();
    confirmMock.confirmDialog.mockResolvedValue(false);
    const wrapper = await mountTermbase();
    await viewButton(wrapper, 'suspect').trigger('click');
    await wrapper.find('[data-term-select-all]').setValue(true);
    await wrapper.find('[data-term-bulk-reject]').trigger('click');
    await flushPromises();
    expect(apiMock.batchConceptStatus).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('restores a rejected term from the detail panel', async () => {
    prime();
    confirmMock.confirmDialog.mockResolvedValue(true);
    const wrapper = await mountTermbase();
    await viewButton(wrapper, 'rejected').trigger('click');
    await wrapper.find('[data-term-row]').trigger('click');
    await wrapper.find('[data-term-restore]').trigger('click');
    await flushPromises();
    expect(apiMock.updateConcept).toHaveBeenCalledWith('d', { status: 'restore' });
    wrapper.unmount();
  });
});

describe('termbase page: import and create panels are visible when opened', () => {
  it('renders the panels above the list and reads a chosen CSV file', async () => {
    prime();
    const wrapper = await mountTermbase();
    await wrapper.find('[data-term-action="import"]').trigger('click');
    const html = wrapper.html();
    expect(html.indexOf('qy-import-callout')).toBeLessThan(html.indexOf('qy-term-layout'));
    const file = new File(['source,target\nfoo,某'], 'terms.csv', { type: 'text/csv' });
    const input = wrapper.find('[data-term-import-file]');
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true });
    await input.trigger('change');
    await flushPromises();
    expect(wrapper.find('[data-term-import-filename]').text()).toContain('terms.csv');
    expect(wrapper.find('.qy-import-callout textarea').element.value).toContain('foo,某');
    await wrapper.find('[data-term-action="create"]').trigger('click');
    const panels = wrapper.html();
    expect(panels.indexOf('data-new-term-form')).toBeLessThan(panels.indexOf('qy-term-layout'));
    wrapper.unmount();
  });
});

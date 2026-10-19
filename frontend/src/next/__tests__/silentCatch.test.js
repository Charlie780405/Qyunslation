import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia } from 'pinia';

const apiMock = vi.hoisted(() => ({
  listTerms: vi.fn(),
  getPreferences: vi.fn(),
  listPreflights: vi.fn(),
  getUploadSession: vi.fn(),
}));
vi.mock('../api.js', () => ({ api: apiMock }));

import TermbasePage from '../pages/TermbasePage.vue';
import { restoreWorkbenchSession, uploadStorageKey } from '../stores/workbench.js';

afterEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  document.body.innerHTML = '';
});

async function mountTermbase() {
  const router = createRouter({ history: createMemoryHistory('/next'), routes: [{ path: '/termbase', component: TermbasePage }, { path: '/:p(.*)*', component: { template: '<div />' } }] });
  router.push('/termbase');
  await router.isReady();
  const wrapper = mount(TermbasePage, { attachTo: document.body, global: { plugins: [router, createPinia()] } });
  await flushPromises();
  return wrapper;
}

describe('termbase page load failures', () => {
  it('says so instead of showing an empty vocabulary', async () => {
    apiMock.listTerms.mockRejectedValue(Object.assign(new Error('boom'), { network: true }));
    const wrapper = await mountTermbase();
    expect(wrapper.find('[data-term-load-error]').text()).toContain('连接中断');
    apiMock.listTerms.mockResolvedValue({ items: [] });
    await wrapper.find('[data-term-load-error] button').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-term-load-error]').exists()).toBe(false);
    wrapper.unmount();
  });
});

describe('pending upload pointer', () => {
  const user = { tenant_slug: 't', sub: 'u' };
  const key = uploadStorageKey('t', 'u');

  function prime() {
    apiMock.getPreferences.mockResolvedValue({ preferences: {} });
    apiMock.listPreflights.mockResolvedValue({ latest: null });
    window.localStorage.setItem(key, 'upload-1');
  }

  it('is kept when the connection drops while checking it', async () => {
    prime();
    apiMock.getUploadSession.mockRejectedValue(Object.assign(new Error('offline'), { network: true }));
    await restoreWorkbenchSession(user);
    expect(window.localStorage.getItem(key)).toBe('upload-1');
  });

  it('is dropped when the server says the upload is gone', async () => {
    prime();
    apiMock.getUploadSession.mockRejectedValue(Object.assign(new Error('gone'), { status: 404 }));
    await restoreWorkbenchSession(user);
    expect(window.localStorage.getItem(key)).toBeNull();
  });
});

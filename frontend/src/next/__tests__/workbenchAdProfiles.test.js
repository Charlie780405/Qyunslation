import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia, setActivePinia } from 'pinia';

const apiMock = vi.hoisted(() => ({
  me: vi.fn(),
  listModelProfiles: vi.fn(async () => ({ profiles: [] })),
  listRuns: vi.fn(async () => ({ items: [] })),
  getRunEvents: vi.fn(async () => ({ items: [] })),
  getPreferences: vi.fn(async () => ({})),
  savePreferences: vi.fn(async () => ({})),
  listPreflights: vi.fn(async () => ({ items: [], latest: null })),
}));
vi.mock('../api.js', () => ({ api: apiMock }));

import WorkbenchPage from '../pages/WorkbenchPage.vue';
import { useSessionStore } from '../stores/session.js';
import { workbenchState } from '../stores/workbench.js';

async function mountWorkbench({ adEnabled }) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.user = { display_name: 'tester', capabilities: { ad_enabled: adEnabled, workbench_v2: true } };
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

afterEach(() => {
  document.body.innerHTML = '';
  workbenchState.domainProfile = 'general';
  workbenchState.profile = '临床研究文档';
});

describe('workbench AD document profiles', () => {
  it('hides the AD option when the tenant is not enabled', async () => {
    const wrapper = await mountWorkbench({ adEnabled: false });
    const options = wrapper.findAll('select option').map((option) => option.text());
    expect(options).not.toContain('AD 特应性皮炎');
    wrapper.unmount();
  });

  it('switches document profiles to the two AD-supported ones and back', async () => {
    const wrapper = await mountWorkbench({ adEnabled: true });
    workbenchState.profile = '监管申报材料';
    workbenchState.domainProfile = 'ad';
    await flushPromises();
    expect(workbenchState.profile).toBe('临床研究文档');
    expect(wrapper.text()).toContain('AD 内部测试版');
    workbenchState.profile = '医学研究文献';
    workbenchState.domainProfile = 'general';
    await flushPromises();
    expect(workbenchState.profile).toBe('临床研究文档');
    wrapper.unmount();
  });
});

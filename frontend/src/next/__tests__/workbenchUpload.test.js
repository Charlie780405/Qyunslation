import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia, setActivePinia } from 'pinia';

const apiMock = vi.hoisted(() => ({
  me: vi.fn(),
  listModelProfiles: vi.fn(async () => ({
    profiles: [
      { profile_id: 'internal-qwen-quality', label: '内网 Qwen', configured: true, role: 'translator' },
    ],
  })),
  listRuns: vi.fn(async () => ({ items: [] })),
  getRunEvents: vi.fn(async () => ({ items: [] })),
  getPreferences: vi.fn(async () => ({})),
  savePreferences: vi.fn(async () => ({})),
  listPreflights: vi.fn(async () => ({ items: [], latest: null })),
  uploadPreflightResumable: vi.fn(),
  createTranslationRun: vi.fn(async () => ({ id: 'run-1' })),
}));
vi.mock('../api.js', () => ({ api: apiMock }));
// Hashing is covered in fileHash.test.js; here it would only add timing to the upload flow.
vi.mock('../lib/fileHash.js', () => ({ sha256Hex: async () => null }));

import WorkbenchPage from '../pages/WorkbenchPage.vue';
import { useSessionStore } from '../stores/session.js';
import { workbenchState } from '../stores/workbench.js';

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

function dropFiles(wrapper, files) {
  return wrapper.find('.qy-dropzone').trigger('drop', { dataTransfer: { files, types: ['Files'] } });
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.clearAllMocks();
  workbenchState.bilingual = true;
  workbenchState.classification = 'internal';
  workbenchState.modelProfileId = 'internal-qwen-quality';
});

describe('workbench drag and drop', () => {
  it('accepts a dropped supported file', async () => {
    const wrapper = await mountWorkbench();
    await dropFiles(wrapper, [new File(['%PDF-1.7'], 'protocol.pdf', { type: 'application/pdf' })]);
    await flushPromises();
    expect(wrapper.find('.qy-dropzone').text()).toContain('protocol.pdf');
    expect(wrapper.find('.qy-panel-actions button').attributes('disabled')).toBeUndefined();
    wrapper.unmount();
  });

  it('rejects a dropped unsupported file with a visible reason', async () => {
    const wrapper = await mountWorkbench();
    await dropFiles(wrapper, [new File(['x'], 'archive.zip', { type: 'application/zip' })]);
    await flushPromises();
    expect(wrapper.find('.qy-dropzone').text()).not.toContain('archive.zip');
    expect(wrapper.text()).toContain('不支持的文件格式');
    wrapper.unmount();
  });

  it('uses only the first file when several are dropped and says so', async () => {
    const wrapper = await mountWorkbench();
    await dropFiles(wrapper, [
      new File(['a'], 'first.docx'),
      new File(['b'], 'second.docx'),
    ]);
    await flushPromises();
    expect(wrapper.find('.qy-dropzone').text()).toContain('first.docx');
    expect(wrapper.text()).toContain('一次只能处理一个文件');
    wrapper.unmount();
  });

  it('highlights the drop target while a file is dragged over it', async () => {
    const wrapper = await mountWorkbench();
    const zone = wrapper.find('.qy-dropzone');
    await zone.trigger('dragover', { dataTransfer: { types: ['Files'] } });
    expect(zone.classes()).toContain('is-dragging');
    await zone.trigger('dragleave', { relatedTarget: null });
    expect(zone.classes()).not.toContain('is-dragging');
    wrapper.unmount();
  });

  it('advertises the same formats the server accepts', async () => {
    const wrapper = await mountWorkbench();
    const accept = wrapper.find('#workbench-file').attributes('accept');
    for (const ext of ['.pdf', '.docx', '.pptx', '.txt', '.md', '.png', '.jpg', '.jpeg']) {
      expect(accept).toContain(ext);
    }
    wrapper.unmount();
  });
});

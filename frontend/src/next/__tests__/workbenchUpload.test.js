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

describe('workbench output mode and request identity', () => {
  async function readyPreflight(wrapper, name) {
    apiMock.uploadPreflightResumable.mockResolvedValue({
      id: 'pf-1', state: 'ready', filename: name, format: name.split('.').pop(), size_bytes: 10,
    });
    await dropFiles(wrapper, [new File(['x'], name)]);
    await wrapper.find('.qy-panel-actions button').trigger('click');
    await flushPromises();
  }

  it('disables the bilingual option for formats that cannot produce it', async () => {
    const wrapper = await mountWorkbench();
    await wrapper.find('.qy-page-head-actions button').trigger('click');
    await readyPreflight(wrapper, 'notes.txt');
    const box = wrapper.find('input[data-field="bilingual"]');
    expect(box.attributes('disabled')).toBeDefined();
    expect(wrapper.text()).toContain('仅 PDF 支持源译对照');
    wrapper.unmount();
  });

  it('keeps the bilingual option for PDF', async () => {
    const wrapper = await mountWorkbench();
    await wrapper.find('.qy-page-head-actions button').trigger('click');
    await readyPreflight(wrapper, 'protocol.pdf');
    expect(wrapper.find('input[data-field="bilingual"]').attributes('disabled')).toBeUndefined();
    wrapper.unmount();
  });

  it('puts model, classification and output mode into the idempotency key', async () => {
    const wrapper = await mountWorkbench();
    await readyPreflight(wrapper, 'protocol.pdf');
    const start = wrapper.findAll('.qy-preflight-card button').at(-1);
    await start.trigger('click');
    await flushPromises();
    const firstKey = apiMock.createTranslationRun.mock.calls[0][1];
    expect(firstKey).toContain(encodeURIComponent('internal-qwen-quality'));
    expect(firstKey).toContain('internal');
    wrapper.unmount();

    vi.clearAllMocks();
    const second = await mountWorkbench();
    workbenchState.classification = 'public';
    workbenchState.bilingual = false;
    await readyPreflight(second, 'protocol.pdf');
    await second.findAll('.qy-preflight-card button').at(-1).trigger('click');
    await flushPromises();
    expect(apiMock.createTranslationRun.mock.calls[0][1]).not.toBe(firstKey);
    second.unmount();
  });
});

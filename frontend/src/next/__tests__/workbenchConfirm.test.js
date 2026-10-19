import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia, setActivePinia } from 'pinia';

const apiMock = vi.hoisted(() => ({
  me: vi.fn(),
  listModelProfiles: vi.fn(),
  listRuns: vi.fn(),
  getRunEvents: vi.fn(),
  getPreferences: vi.fn(),
  savePreferences: vi.fn(),
  listPreflights: vi.fn(),
  uploadPreflightResumable: vi.fn(),
  validateRun: vi.fn(),
  createTranslationRun: vi.fn(),
  createRevision: vi.fn(),
  resumeRun: vi.fn(),
  retryRun: vi.fn(),
  copyPreflight: vi.fn(),
  patchRun: vi.fn(),
}));
vi.mock('../api.js', () => ({ api: apiMock }));
// Hashing is covered in fileHash.test.js; here it would only add timing to the upload flow.
vi.mock('../lib/fileHash.js', () => ({ sha256Hex: async () => null }));

import WorkbenchPage from '../pages/WorkbenchPage.vue';
import { useSessionStore } from '../stores/session.js';
import { workbenchState } from '../stores/workbench.js';

const QWEN = { profile_id: 'internal-qwen-quality', label: '内网 Qwen 质量档', role: 'translator', provider: 'ollama', configured: true };
const READY = { id: 'pf-1', state: 'ready', filename: 'protocol.pdf', format: 'pdf', size_bytes: 2048 };
const OK = {
  ok: true, errors: [], warnings: [], config_digest: 'd'.repeat(64),
  config: { model: { label: '内网 Qwen 质量档' }, term_model: { label: '内网 Qwen（术语抽取）' }, egress_scope: 'none', qa_policy: {} },
  preflight: { id: 'pf-1', state: 'ready', used_by_run_id: null },
};

function run(overrides) {
  return {
    id: 'r1', filename: 'old.pdf', format: 'pdf', display_name: '旧任务', source_language: 'English', target_language: '简体中文',
    status: 'failed', stage: 'qa', quality_state: 'draft', progress: null, artifacts: [], lifecycle: 'failed',
    document_classification: 'confidential', model_profile_id: 'internal-qwen-quality', preflight_id: 'pf-old',
    settings: { source_language: 'English', target_language: '简体中文', profile: '监管申报材料', domain_profile: 'general', bilingual: false, pipeline: 'v2' },
    allowed_actions: ['open', 'rename', 'archive', 'delete', 'retry', 'revise'], pending_counts: {}, ...overrides,
  };
}

async function mountPage({ runs = [], latest = null } = {}) {
  apiMock.listRuns.mockResolvedValue({ items: runs });
  apiMock.listPreflights.mockResolvedValue({ items: latest ? [latest] : [], latest });
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.user = { display_name: 'tester', capabilities: { workbench_v2: true, ad_enabled: true } };
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
  return { wrapper, router };
}

const drawer = () => document.body.querySelector('[data-run-confirm]');
const inDrawer = (selector) => drawer().querySelector(selector);
const byText = (root, text) => [...root.querySelectorAll('button')].find((b) => b.textContent.includes(text));

async function readyPreflight(wrapper) {
  apiMock.uploadPreflightResumable.mockResolvedValue(READY);
  const input = wrapper.find('#workbench-file');
  Object.defineProperty(input.element, 'files', { value: [new File(['%PDF'], 'protocol.pdf')], configurable: true });
  await input.trigger('change');
  await wrapper.find('.qy-panel-actions button').trigger('click');
  await flushPromises();
}

beforeEach(() => {
  apiMock.listModelProfiles.mockResolvedValue({ items: [QWEN] });
  apiMock.getRunEvents.mockResolvedValue({ items: [] });
  apiMock.getPreferences.mockResolvedValue({ preferences: { workbench: { sourceLanguage: 'English', targetLanguage: '简体中文', profile: '临床研究文档', domainProfile: 'general', bilingual: true, classification: 'internal', modelProfileId: 'internal-qwen-quality' } } });
  apiMock.savePreferences.mockResolvedValue({});
  apiMock.validateRun.mockResolvedValue(OK);
  apiMock.createTranslationRun.mockResolvedValue({ id: 'run-new' });
  apiMock.createRevision.mockResolvedValue({ id: 'run-v2' });
  apiMock.resumeRun.mockResolvedValue({});
});

afterEach(() => {
  document.body.innerHTML = '';
  vi.clearAllMocks();
  workbenchState.classification = 'internal';
  workbenchState.profile = '临床研究文档';
  workbenchState.bilingual = true;
});

describe('every start goes through the confirmation drawer', () => {
  it('opens the drawer instead of starting, and starts only after the person confirms', async () => {
    const { wrapper } = await mountPage();
    await readyPreflight(wrapper);
    const open = wrapper.find('.qy-preflight-card button.qy-primary-button');
    expect(open.text()).toContain('确认参数');
    await open.trigger('click');
    await flushPromises();
    expect(drawer()).not.toBeNull();
    expect(apiMock.createTranslationRun).not.toHaveBeenCalled();
    byText(drawer(), '确认并开始翻译').click();
    await flushPromises();
    expect(apiMock.createTranslationRun).toHaveBeenCalledTimes(1);
    const [payload, key] = apiMock.createTranslationRun.mock.calls[0];
    expect(payload).toMatchObject({ preflight_id: 'pf-1', config_digest: 'd'.repeat(64), document_classification: 'internal' });
    expect(key).toBeTruthy();
    expect(drawer()).toBeNull();
    wrapper.unmount();
  });

  it('has no second copy of the settings on the page itself', async () => {
    const { wrapper } = await mountPage();
    expect(wrapper.find('.qy-upload-panel select').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('本次任务参数');
    expect(wrapper.find('.qy-settings-card').exists()).toBe(false);
    wrapper.unmount();
  });

  it('never saves defaults just because a field was changed', async () => {
    const { wrapper } = await mountPage();
    await readyPreflight(wrapper);
    await wrapper.find('.qy-preflight-card button.qy-primary-button').trigger('click');
    await flushPromises();
    const select = inDrawer('[data-field="classification"]');
    select.value = 'confidential';
    select.dispatchEvent(new Event('change'));
    await flushPromises();
    await new Promise((resolve) => setTimeout(resolve, 900)); // longer than the old auto-save delay
    expect(apiMock.savePreferences).not.toHaveBeenCalled();
    byText(drawer(), '确认并开始翻译').click();
    await flushPromises();
    expect(apiMock.savePreferences).not.toHaveBeenCalled(); // "this task only" is the default
    wrapper.unmount();
  });

  it('saves defaults only when asked, and says so when saving fails', async () => {
    apiMock.savePreferences.mockRejectedValueOnce(new Error('保存服务暂不可用'));
    const { wrapper } = await mountPage();
    await readyPreflight(wrapper);
    await wrapper.find('.qy-preflight-card button.qy-primary-button').trigger('click');
    await flushPromises();
    const radio = inDrawer('input[name="save-mode"][value="default"]');
    radio.checked = true;
    radio.dispatchEvent(new Event('change'));
    await flushPromises();
    byText(drawer(), '确认并开始翻译').click();
    await flushPromises();
    expect(apiMock.createTranslationRun).toHaveBeenCalledTimes(1); // the task exists either way
    expect(apiMock.savePreferences).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain('默认参数保存失败');
    expect(wrapper.text()).toContain('保存服务暂不可用');
    wrapper.unmount();
  });

  it('a stale confirmation is explained and nothing is hidden', async () => {
    apiMock.createTranslationRun.mockRejectedValueOnce(
      Object.assign(new Error('确认之后配置已发生变化，请重新确认参数'), { status: 409, payload: { detail: { code: 'CONFIG_STALE' } } }),
    );
    const { wrapper } = await mountPage();
    await readyPreflight(wrapper);
    await wrapper.find('.qy-preflight-card button.qy-primary-button').trigger('click');
    await flushPromises();
    byText(drawer(), '确认并开始翻译').click();
    await flushPromises();
    expect(drawer()).not.toBeNull(); // still open for a new decision
    expect(inDrawer('[data-submit-error]').textContent).toContain('请重新确认参数');
    wrapper.unmount();
  });

  it('copies the pre-check when the file already has a task and revalidates the copy', async () => {
    apiMock.validateRun
      .mockResolvedValueOnce({ ...OK, ok: false, config_digest: null, errors: [{ code: 'PREFLIGHT_ALREADY_RUN', message: '该文件已创建过任务', field: 'preflight_id', run_id: 'r9', can_copy: true }] })
      .mockResolvedValue({ ...OK, preflight: { id: 'pf-copy', state: 'ready', used_by_run_id: null } });
    apiMock.copyPreflight.mockResolvedValue({ ...READY, id: 'pf-copy' });
    const { wrapper } = await mountPage();
    await readyPreflight(wrapper);
    await wrapper.find('.qy-preflight-card button.qy-primary-button').trigger('click');
    await flushPromises();
    inDrawer('[data-copy-preflight]').click();
    await flushPromises();
    expect(apiMock.copyPreflight).toHaveBeenCalledWith('pf-1');
    expect(apiMock.validateRun).toHaveBeenLastCalledWith(expect.objectContaining({ preflight_id: 'pf-copy' }));
    wrapper.unmount();
  });

  it('does not offer a pre-check that already has a task as ready to start', async () => {
    const { wrapper } = await mountPage({ latest: { ...READY, used_by_run_id: 'r-old' } });
    expect(wrapper.text()).not.toContain('已恢复上次预检结果');
    wrapper.unmount();
  });

  it('gives focus back to the button that opened the drawer', async () => {
    const { wrapper } = await mountPage();
    await readyPreflight(wrapper);
    const opener = wrapper.find('.qy-preflight-card button.qy-primary-button');
    opener.element.focus();
    await opener.trigger('click');
    await flushPromises();
    drawer().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await flushPromises();
    expect(drawer()).toBeNull();
    expect(document.activeElement).toBe(opener.element);
    wrapper.unmount();
  });
});

describe('retry, resume and copy also confirm', () => {
  it('retrying shows the frozen configuration and creates a new version with only the changes', async () => {
    const { wrapper } = await mountPage({ runs: [run({})] });
    const retry = [...wrapper.findAll('.qy-task-row button')].find((b) => b.text() === '重试');
    await retry.trigger('click');
    await flushPromises();
    expect(drawer()).not.toBeNull();
    expect(drawer().textContent).toContain('冻结');
    expect(apiMock.createRevision).not.toHaveBeenCalled();
    expect(apiMock.retryRun).not.toHaveBeenCalled();
    const bilingual = inDrawer('[data-field="bilingual"]');
    bilingual.checked = true;
    bilingual.dispatchEvent(new Event('change'));
    await flushPromises();
    byText(drawer(), '确认并生成修订版').click();
    await flushPromises();
    expect(apiMock.createRevision).toHaveBeenCalledWith('r1', { overrides: { bilingual: true } });
    wrapper.unmount();
  });

  it('retrying without changes sends no overrides', async () => {
    const { wrapper } = await mountPage({ runs: [run({})] });
    await [...wrapper.findAll('.qy-task-row button')].find((b) => b.text() === '重试').trigger('click');
    await flushPromises();
    byText(drawer(), '确认并生成修订版').click();
    await flushPromises();
    expect(apiMock.createRevision).toHaveBeenCalledWith('r1', {});
    wrapper.unmount();
  });

  it('the legacy-unverified "new pipeline retry" keeps asking for the new pipeline', async () => {
    const legacy = run({ status: 'succeeded', lifecycle: 'completed', quality_state: 'legacy_unverified' });
    const { wrapper } = await mountPage({ runs: [legacy] });
    await [...wrapper.findAll('.qy-task-row button')].find((b) => b.text() === '新版重试').trigger('click');
    await flushPromises();
    byText(drawer(), '确认并生成修订版').click();
    await flushPromises();
    expect(apiMock.createRevision).toHaveBeenCalledWith('r1', { pipeline: 'v2' });
    wrapper.unmount();
  });

  it('resuming asks for confirmation of the frozen configuration first', async () => {
    const interrupted = run({ status: 'interrupted', lifecycle: 'interrupted', allowed_actions: ['open', 'resume', 'archive', 'delete', 'retry'] });
    const { wrapper } = await mountPage({ runs: [interrupted] });
    await [...wrapper.findAll('.qy-task-row button')].find((b) => b.text() === '续跑').trigger('click');
    await flushPromises();
    expect(apiMock.resumeRun).not.toHaveBeenCalled();
    byText(drawer(), '按原配置续跑').click();
    await flushPromises();
    expect(apiMock.resumeRun).toHaveBeenCalledWith('r1');
    wrapper.unmount();
  });

  it('copying a task\'s configuration carries it into the next confirmation, labelled as copied', async () => {
    const { wrapper } = await mountPage({ runs: [run({})] });
    await [...wrapper.findAll('.qy-task-row button')].find((b) => b.text() === '复制配置').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('已载入');
    await readyPreflight(wrapper);
    await wrapper.find('.qy-preflight-card button.qy-primary-button').trigger('click');
    await flushPromises();
    expect(inDrawer('[data-field="classification"]').value).toBe('confidential');
    expect(inDrawer('[data-field="profile"]').value).toBe('监管申报材料');
    expect(drawer().textContent).toContain('复制自');
    wrapper.unmount();
  });
});

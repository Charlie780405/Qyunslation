import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import axe from 'axe-core';

const apiMock = vi.hoisted(() => ({
  validateRun: vi.fn(),
  listModelProfiles: vi.fn(),
}));
vi.mock('../api.js', () => ({ api: apiMock }));

import RunConfirmDrawer from '../components/RunConfirmDrawer.vue';

const PROFILES = {
  internal: [
    { profile_id: 'internal-qwen-quality', label: '内网 Qwen 质量档', role: 'translator', provider: 'ollama', configured: true },
    { profile_id: 'term-internal-qwen', label: '内网 Qwen（术语抽取，无外发）', role: 'term_suggester', provider: 'ollama', configured: true },
  ],
  confidential: [
    { profile_id: 'internal-qwen-quality', label: '内网 Qwen 质量档', role: 'translator', provider: 'ollama', configured: true },
  ],
  public: [
    { profile_id: 'internal-qwen-quality', label: '内网 Qwen 质量档', role: 'translator', provider: 'ollama', configured: true },
    { profile_id: 'public-deepseek-flash', label: 'DeepSeek Flash（公开资料）', role: 'translator', provider: 'deepseek', configured: false, experimental: true },
  ],
};

const DEFAULTS = {
  displayName: '', sourceLanguage: 'English', targetLanguage: '简体中文', profile: '临床研究文档',
  domainProfile: 'general', classification: 'internal', modelProfileId: 'internal-qwen-quality', bilingual: true,
};
const PREFLIGHT = { id: 'pf-1', filename: 'protocol.pdf', format: 'pdf', size_bytes: 2048, state: 'ready' };

function okResponse(overrides = {}) {
  return {
    ok: true, errors: [], warnings: [], config_digest: 'd'.repeat(64),
    config: {
      model: { label: '内网 Qwen 质量档' }, term_model: { label: '内网 Qwen（术语抽取，无外发）' },
      egress_scope: 'none', bilingual_effective: true,
      qa_policy: { deterministic: true, term_extraction: true, term_model_profile_id: 'term-internal-qwen' },
    },
    preflight: { id: 'pf-1', state: 'ready', used_by_run_id: null },
    ...overrides,
  };
}

function mountDrawer(props = {}) {
  return mount(RunConfirmDrawer, {
    attachTo: document.body,
    props: {
      mode: 'new', preflight: PREFLIGHT, initial: { ...DEFAULTS }, defaults: { ...DEFAULTS }, last: null,
      adEnabled: true, onSubmit: vi.fn(async () => ({})), ...props,
    },
  });
}

const root = (wrapper) => wrapper.find('[data-run-confirm]');
const field = (wrapper, name) => wrapper.find(`[data-field="${name}"]`);
const row = (wrapper, name) => wrapper.find(`[data-field-row="${name}"]`);
const confirm = (wrapper) => wrapper.find('[data-confirm]');

beforeEach(() => {
  apiMock.listModelProfiles.mockImplementation(async (classification) => ({ items: PROFILES[classification] || PROFILES.internal }));
  apiMock.validateRun.mockResolvedValue(okResponse());
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
  document.body.innerHTML = '';
});

describe('RunConfirmDrawer (new task)', () => {
  it('shows the file and every setting that will actually be used', async () => {
    const wrapper = mountDrawer();
    await flushPromises();
    const text = root(wrapper).text();
    expect(text).toContain('protocol.pdf');
    for (const name of ['name', 'sourceLanguage', 'targetLanguage', 'profile', 'domainProfile', 'classification', 'modelProfileId', 'bilingual']) {
      expect(field(wrapper, name).exists(), name).toBe(true);
    }
    expect(wrapper.find('[data-qa-policy]').text()).toContain('确定性 QA');
    expect(wrapper.find('[data-qa-policy]').text()).toContain('内网 Qwen（术语抽取，无外发）');
    expect(root(wrapper).text()).toContain('外发范围：无');
    wrapper.unmount();
  });

  it('asks the server to validate what is on screen, and waits for the answer before allowing the start', async () => {
    let release;
    apiMock.validateRun.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    const wrapper = mountDrawer();
    await flushPromises();
    expect(apiMock.validateRun).toHaveBeenCalledWith(expect.objectContaining({
      preflight_id: 'pf-1', source_language: 'English', target_language: '简体中文', profile: '临床研究文档',
      domain_profile: 'general', document_classification: 'internal', model_profile_id: 'internal-qwen-quality', bilingual: true,
    }));
    expect(confirm(wrapper).attributes('disabled')).toBeDefined();
    expect(wrapper.find('[data-disabled-reason]').text()).toContain('正在校验');
    release(okResponse());
    await flushPromises();
    expect(confirm(wrapper).attributes('disabled')).toBeUndefined();
    expect(wrapper.find('[data-disabled-reason]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('lists every problem, blocks the start and says why', async () => {
    apiMock.validateRun.mockResolvedValue(okResponse({
      ok: false, config_digest: null,
      errors: [
        { code: 'LANGUAGE_SAME', message: '源语言和目标语言不能相同', field: 'language' },
        { code: 'MODEL_NOT_ALLOWED', message: '该资料等级不允许使用所选翻译模型', field: 'model_profile_id' },
      ],
    }));
    const wrapper = mountDrawer();
    await flushPromises();
    const alerts = wrapper.findAll('[data-validation] [role="alert"]');
    expect(alerts).toHaveLength(2);
    expect(alerts[0].text()).toContain('源语言和目标语言不能相同');
    expect(confirm(wrapper).attributes('disabled')).toBeDefined();
    expect(wrapper.find('[data-disabled-reason]').text()).toContain('2 个问题');
    wrapper.unmount();
  });

  it('shows warnings without blocking the start', async () => {
    apiMock.validateRun.mockResolvedValue(okResponse({
      warnings: [{ code: 'BILINGUAL_NOT_SUPPORTED', message: '该格式只输出译文，不会生成源译对照稿', field: 'bilingual' }],
    }));
    const wrapper = mountDrawer();
    await flushPromises();
    expect(wrapper.find('[data-warning]').text()).toContain('只输出译文');
    expect(confirm(wrapper).attributes('disabled')).toBeUndefined();
    wrapper.unmount();
  });

  it('says where each value came from and how it differs from the default', async () => {
    const wrapper = mountDrawer({ initial: { ...DEFAULTS, classification: 'confidential' } });
    await flushPromises();
    expect(row(wrapper, 'profile').text()).toContain('默认');
    expect(row(wrapper, 'classification').text()).toContain('与默认值不同');
    expect(row(wrapper, 'classification').text()).toContain('内部');
    await field(wrapper, 'profile').setValue('监管申报材料');
    expect(row(wrapper, 'profile').text()).toContain('本次修改');
    expect(row(wrapper, 'profile').text()).toContain('与默认值不同');
    wrapper.unmount();
  });

  it('can reuse the last task\'s configuration and labels it as such', async () => {
    const last = { ...DEFAULTS, profile: '监管申报材料', targetLanguage: 'English', sourceLanguage: '简体中文', label: '上次任务' };
    const wrapper = mountDrawer({ last });
    await flushPromises();
    await wrapper.find('[data-use-last]').trigger('click');
    await flushPromises();
    expect(field(wrapper, 'profile').element.value).toBe('监管申报材料');
    expect(row(wrapper, 'profile').text()).toContain('上次使用');
    wrapper.unmount();
  });

  it('replaces an unusable model and tells the person so', async () => {
    const wrapper = mountDrawer({ initial: { ...DEFAULTS, classification: 'public', modelProfileId: 'public-deepseek-flash' } });
    await flushPromises();
    expect(field(wrapper, 'modelProfileId').element.value).toBe('internal-qwen-quality');
    expect(row(wrapper, 'modelProfileId').text()).toContain('原选择的模型不可用');
    wrapper.unmount();
  });

  it('reloads the model list when the data class changes and keeps only usable models', async () => {
    const wrapper = mountDrawer();
    await flushPromises();
    await field(wrapper, 'classification').setValue('confidential');
    await flushPromises();
    expect(apiMock.listModelProfiles).toHaveBeenLastCalledWith('confidential');
    const options = field(wrapper, 'modelProfileId').findAll('option').map((o) => o.text());
    expect(options).toEqual(['内网 Qwen 质量档']);
    wrapper.unmount();
  });

  it('disables the pair output for formats that cannot produce it', async () => {
    const wrapper = mountDrawer({ preflight: { ...PREFLIGHT, filename: 'notes.txt', format: 'txt' } });
    await flushPromises();
    expect(field(wrapper, 'bilingual').attributes('disabled')).toBeDefined();
    expect(root(wrapper).text()).toContain('仅 PDF 支持源译对照');
    wrapper.unmount();
  });

  it('defaults to "this task only" and saves defaults only when asked', async () => {
    const onSubmit = vi.fn(async () => ({}));
    const wrapper = mountDrawer({ onSubmit });
    await flushPromises();
    const once = wrapper.find('input[name="save-mode"][value="once"]');
    expect(once.element.checked).toBe(true);
    await confirm(wrapper).trigger('click');
    await flushPromises();
    expect(onSubmit.mock.calls[0][0].saveAsDefault).toBe(false);
    wrapper.unmount();

    const second = vi.fn(async () => ({}));
    const again = mountDrawer({ onSubmit: second });
    await flushPromises();
    await again.find('input[name="save-mode"][value="default"]').setValue(true);
    await confirm(again).trigger('click');
    await flushPromises();
    expect(second.mock.calls[0][0].saveAsDefault).toBe(true);
    again.unmount();
  });

  it('submits exactly what was validated, with its digest, and only once for a double click', async () => {
    let finish;
    const onSubmit = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    const wrapper = mountDrawer({ onSubmit });
    await flushPromises();
    await field(wrapper, 'name').setValue('我的任务');
    await vi.waitFor(() => expect(apiMock.validateRun).toHaveBeenCalledTimes(2));
    await flushPromises();
    await confirm(wrapper).trigger('click');
    await confirm(wrapper).trigger('click');
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const sent = onSubmit.mock.calls[0][0];
    expect(sent.payload).toMatchObject({
      preflight_id: 'pf-1', display_name: '我的任务', document_classification: 'internal',
      model_profile_id: 'internal-qwen-quality', config_digest: 'd'.repeat(64),
    });
    expect(sent.key).toMatch(/\S{8,}/);
    finish({});
    await flushPromises();
    wrapper.unmount();
  });

  it('uses a different request key when the configuration changes, the same one when it does not', async () => {
    const onSubmit = vi.fn(async () => { throw new Error('网络中断'); });
    const wrapper = mountDrawer({ onSubmit });
    await flushPromises();
    await confirm(wrapper).trigger('click');
    await flushPromises();
    await confirm(wrapper).trigger('click');
    await flushPromises();
    expect(onSubmit.mock.calls[0][0].key).toBe(onSubmit.mock.calls[1][0].key); // a retry of the same decision
    apiMock.validateRun.mockResolvedValue(okResponse({ config_digest: 'e'.repeat(64) }));
    await field(wrapper, 'profile').setValue('监管申报材料');
    await vi.waitFor(() => expect(apiMock.validateRun).toHaveBeenCalledTimes(2));
    await flushPromises();
    await confirm(wrapper).trigger('click');
    await flushPromises();
    expect(onSubmit.mock.calls[2][0].key).not.toBe(onSubmit.mock.calls[0][0].key);
    wrapper.unmount();
  });

  it('shows a failed submission and stays open so it can be tried again', async () => {
    const onSubmit = vi.fn(async () => { throw new Error('网络连接失败'); });
    const wrapper = mountDrawer({ onSubmit });
    await flushPromises();
    await confirm(wrapper).trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-submit-error]').text()).toContain('网络连接失败');
    expect(confirm(wrapper).attributes('disabled')).toBeUndefined();
    expect(wrapper.emitted('close')).toBeUndefined();
    wrapper.unmount();
  });

  it('asks again when the configuration changed after it was confirmed', async () => {
    const stale = Object.assign(new Error('确认之后配置已发生变化，请重新确认参数'), { status: 409, payload: { detail: { code: 'CONFIG_STALE' } } });
    const onSubmit = vi.fn(async () => { throw stale; });
    const wrapper = mountDrawer({ onSubmit });
    await flushPromises();
    await confirm(wrapper).trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-submit-error]').text()).toContain('请重新确认参数');
    expect(apiMock.validateRun.mock.calls.length).toBeGreaterThanOrEqual(2); // re-validated against the server
    wrapper.unmount();
  });

  it('offers to copy the pre-check when the file already has a task', async () => {
    apiMock.validateRun.mockResolvedValue(okResponse({
      ok: false, config_digest: null,
      errors: [{ code: 'PREFLIGHT_ALREADY_RUN', message: '该文件已用这份预检创建过任务', field: 'preflight_id', run_id: 'r-1', can_copy: true }],
    }));
    const wrapper = mountDrawer();
    await flushPromises();
    await wrapper.find('[data-copy-preflight]').trigger('click');
    expect(wrapper.emitted('copy-preflight')).toHaveLength(1);
    wrapper.unmount();
  });
});

describe('RunConfirmDrawer (AD domain)', () => {
  it('hides the AD option when the tenant is not enabled', async () => {
    const wrapper = mountDrawer({ adEnabled: false });
    await flushPromises();
    const options = field(wrapper, 'domainProfile').findAll('option').map((option) => option.text());
    expect(options.some((text) => text.includes('AD'))).toBe(false);
    wrapper.unmount();
  });

  it('switches document types to the two AD-supported ones and back', async () => {
    const wrapper = mountDrawer({ initial: { ...DEFAULTS, profile: '监管申报材料' } });
    await flushPromises();
    await field(wrapper, 'domainProfile').setValue('ad');
    await flushPromises();
    const adOptions = field(wrapper, 'profile').findAll('option').map((option) => option.text());
    expect(adOptions).toEqual(['医学研究文献', '临床研究文档']);
    expect(field(wrapper, 'profile').element.value).toBe('临床研究文档'); // 监管申报材料 is not supported by AD
    expect(wrapper.text()).toContain('AD');
    await field(wrapper, 'domainProfile').setValue('general');
    await flushPromises();
    expect(field(wrapper, 'profile').findAll('option').map((option) => option.text())).toEqual(['临床研究文档', '监管申报材料', '通用医药文档']);
    wrapper.unmount();
  });
});

describe('RunConfirmDrawer (keyboard and accessibility)', () => {
  it('is a labelled modal dialog that closes with Escape and gives focus back', async () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const wrapper = mountDrawer();
    await flushPromises();
    const dialog = root(wrapper);
    expect(dialog.attributes('role')).toBe('dialog');
    expect(dialog.attributes('aria-modal')).toBe('true');
    expect(wrapper.find(`#${dialog.attributes('aria-labelledby')}`).text()).toContain('确认本次翻译参数');
    expect(root(wrapper).element.contains(document.activeElement)).toBe(true);
    await dialog.trigger('keydown', { key: 'Escape' });
    expect(wrapper.emitted('close')).toHaveLength(1);
    wrapper.unmount();
    expect(document.activeElement).toBe(opener);
  });

  it('has no serious accessibility violations', async () => {
    const wrapper = mountDrawer();
    await flushPromises();
    const results = await axe.run(root(wrapper).element, { rules: { 'color-contrast': { enabled: false } } });
    expect(results.violations.filter((v) => ['serious', 'critical'].includes(v.impact))).toEqual([]);
    wrapper.unmount();
  });
});

describe('RunConfirmDrawer (new version of a task)', () => {
  const RUN = {
    id: 'run-1', filename: 'protocol.pdf', format: 'pdf', status: 'failed', display_name: '旧任务',
    document_classification: 'internal', model_profile_id: 'internal-qwen-quality',
    settings: {
      source_language: 'English', target_language: '简体中文', profile: '临床研究文档', domain_profile: 'general',
      bilingual: true, config_digest: 'a'.repeat(64),
    },
  };

  it('shows the frozen configuration and lets only the safe parameters change', async () => {
    const wrapper = mountDrawer({ mode: 'revision', run: RUN, preflight: null });
    await flushPromises();
    expect(root(wrapper).text()).toContain('冻结');
    expect(field(wrapper, 'sourceLanguage').exists()).toBe(false); // not editable here
    expect(root(wrapper).text()).toContain('English → 简体中文');
    for (const name of ['classification', 'modelProfileId', 'bilingual', 'name']) {
      expect(field(wrapper, name).exists(), name).toBe(true);
    }
    wrapper.unmount();
  });

  it('sends nothing but what changed', async () => {
    const onSubmit = vi.fn(async () => ({}));
    const wrapper = mountDrawer({ mode: 'revision', run: RUN, preflight: null, onSubmit });
    await flushPromises();
    await confirm(wrapper).trigger('click');
    await flushPromises();
    expect(onSubmit.mock.calls[0][0].overrides).toEqual({});
    await field(wrapper, 'classification').setValue('confidential');
    await flushPromises();
    await field(wrapper, 'bilingual').setValue(false);
    await confirm(wrapper).trigger('click');
    await flushPromises();
    expect(onSubmit.mock.calls[1][0].overrides).toEqual({ document_classification: 'confidential', bilingual: false });
    expect(apiMock.validateRun).not.toHaveBeenCalled(); // the server validates the new version itself
    wrapper.unmount();
  });

  it('explains why an AD task cannot change its model or data class here', async () => {
    const wrapper = mountDrawer({
      mode: 'revision', preflight: null,
      run: { ...RUN, settings: { ...RUN.settings, domain_profile: 'ad' } },
    });
    await flushPromises();
    expect(field(wrapper, 'classification').attributes('disabled')).toBeDefined();
    expect(field(wrapper, 'modelProfileId').attributes('disabled')).toBeDefined();
    expect(root(wrapper).text()).toContain('请从原文件新建任务');
    wrapper.unmount();
  });

  it('resuming only confirms the frozen configuration', async () => {
    const onSubmit = vi.fn(async () => ({}));
    const wrapper = mountDrawer({ mode: 'resume', run: { ...RUN, status: 'interrupted' }, preflight: null, onSubmit });
    await flushPromises();
    expect(field(wrapper, 'classification').exists()).toBe(false);
    expect(confirm(wrapper).text()).toContain('按原配置续跑');
    await confirm(wrapper).trigger('click');
    await flushPromises();
    expect(onSubmit).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia, setActivePinia } from 'pinia';
import axe from 'axe-core';

const apiMock = vi.hoisted(() => ({
  me: vi.fn(),
  listModelProfiles: vi.fn(async () => ({ profiles: [] })),
  listRuns: vi.fn(async () => ({ items: [] })),
  getRunEvents: vi.fn(async () => ({ items: [] })),
  getPreferences: vi.fn(async () => ({})),
  savePreferences: vi.fn(async () => ({})),
  listPreflights: vi.fn(async () => ({ items: [], latest: null })),
  cancelRun: vi.fn(async () => ({})),
  patchRun: vi.fn(async () => ({})),
  deleteRun: vi.fn(async () => ({})),
  restoreRunFromTrash: vi.fn(async () => ({})),
  createRunSelection: vi.fn(),
  batchRuns: vi.fn(),
}));
vi.mock('../api.js', () => ({ api: apiMock }));

import WorkbenchPage from '../pages/WorkbenchPage.vue';
import { useSessionStore } from '../stores/session.js';
import { listView, runList } from '../stores/runs.js';

const FAILED_ACTIONS = ['open', 'rename', 'archive', 'delete', 'retry'];
const RUNNING_ACTIONS = ['open', 'rename', 'cancel'];

function run(id, overrides = {}) {
  return {
    id, filename: `${id}.pdf`, display_name: null, name_version: 0, generation: 1, version_count: 1,
    source_language: 'English', target_language: '简体中文',
    status: 'failed', stage: 'qa', quality_state: 'draft', progress: null, artifacts: [],
    lifecycle: 'failed', allowed_actions: FAILED_ACTIONS, qa_summary: {}, formal_gate: { passed: false },
    ...overrides,
  };
}

const running = (id) => run(id, { status: 'translating', lifecycle: 'executing', allowed_actions: RUNNING_ACTIONS });

function page(items, extra = {}) {
  return { items, next_cursor: null, total: items.length, facets: { lifecycle: {}, total: items.length }, ...extra };
}

async function mountPage(first, path = '/workbench') {
  if (first) apiMock.listRuns.mockResolvedValue(first);
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
  router.push(path);
  await router.isReady();
  const wrapper = mount(WorkbenchPage, { attachTo: document.body, global: { plugins: [router, pinia] } });
  await flushPromises();
  return { wrapper, router };
}

function result(action, items) {
  return {
    action,
    requested: items.length,
    succeeded: items.filter((i) => i.outcome === 'succeeded').length,
    failed: items.filter((i) => i.outcome === 'failed').length,
    skipped: items.filter((i) => i.outcome === 'skipped').length,
    items: items.map((i) => ({ name: i.id, reason_code: '', message: '', ...i })),
    replayed: false,
  };
}

beforeEach(() => {
  runList.reset();
  listView.openedId = '';
});

afterEach(() => {
  document.body.innerHTML = '';
  vi.clearAllMocks();
});

const rowBoxes = (wrapper) => wrapper.findAll('[data-row-select]');
const action = (wrapper, name) => wrapper.find(`[data-batch-action="${name}"]`);

describe('selecting tasks', () => {
  it('ticking rows shows how many are selected and the actions that apply', async () => {
    const { wrapper } = await mountPage(page([run('a'), run('b'), run('c')]));
    expect(wrapper.find('[data-batch-bar]').exists()).toBe(false);
    await rowBoxes(wrapper)[0].setValue(true);
    await rowBoxes(wrapper)[2].setValue(true);
    expect(wrapper.find('[data-batch-scope]').text()).toContain('已选择 2 项');
    expect(action(wrapper, 'archive').exists() && action(wrapper, 'trash').exists()).toBe(true);
    expect(action(wrapper, 'purge').exists()).toBe(false); // bin-only
    await wrapper.find('[data-batch-clear]').trigger('click');
    expect(wrapper.find('[data-batch-bar]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('a click on the checkbox does not open the task', async () => {
    const { wrapper, router } = await mountPage(page([run('a')]));
    await rowBoxes(wrapper)[0].trigger('click');
    expect(router.currentRoute.value.path).toBe('/workbench');
    wrapper.unmount();
  });

  it('"select this page" offers to select every match, and unticking one then excludes it', async () => {
    const { wrapper } = await mountPage(page([run('a'), run('b')], { total: 248, next_cursor: 'c1' }));
    await wrapper.find('[data-select-page]').setValue(true);
    expect(wrapper.find('[data-select-banner]').text()).toContain('已选择本页 2 项');
    apiMock.createRunSelection.mockResolvedValue({ selection_token: 'tok', count: 248, scope: 'active' });
    await wrapper.find('[data-select-all]').trigger('click');
    await flushPromises();
    expect(apiMock.createRunSelection).toHaveBeenCalledWith(expect.objectContaining({ trash: false, archived: 'active', lifecycle: [] }));
    expect(wrapper.find('[data-batch-scope]').text()).toContain('已选择全部 248 条筛选结果');
    await rowBoxes(wrapper)[1].setValue(false);
    expect(wrapper.find('[data-batch-scope]').text()).toContain('排除 1 项，共 247 项');

    apiMock.batchRuns.mockResolvedValue(result('archive', [{ id: 'a', outcome: 'succeeded' }]));
    await action(wrapper, 'archive').trigger('click');
    await flushPromises();
    await wrapper.find('[data-batch-confirm-go]').trigger('click');
    await flushPromises();
    expect(apiMock.batchRuns).toHaveBeenCalledTimes(1);
    const [body, key] = apiMock.batchRuns.mock.calls[0];
    expect(body).toEqual({ action: 'archive', selection_token: 'tok', exclude_ids: ['b'] });
    expect(key).toBeTruthy();
    wrapper.unmount();
  });

  it('changing a filter clears the selection and says so', async () => {
    const { wrapper } = await mountPage(page([run('a'), run('b')]));
    await rowBoxes(wrapper)[0].setValue(true);
    expect(wrapper.find('[data-batch-bar]').exists()).toBe(true);
    await wrapper.find('[data-lifecycle-chip="failed"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-batch-scope]').exists()).toBe(false);
    expect(wrapper.find('[data-select-notice]').text()).toContain('选择已清空');
    wrapper.unmount();
  });

  it('keeps the selection while the list refreshes underneath it', async () => {
    const { wrapper } = await mountPage(page([run('a'), run('b')]));
    await rowBoxes(wrapper)[0].setValue(true);
    await runList.refresh();
    await flushPromises();
    expect(wrapper.find('[data-batch-scope]').text()).toContain('已选择 1 项');
    wrapper.unmount();
  });
});

describe('what the bar offers', () => {
  it('turns an action off, with the reason, when no selected task can take it', async () => {
    const { wrapper } = await mountPage(page([running('r1'), running('r2')]));
    await wrapper.find('[data-select-page]').setValue(true);
    const archive = action(wrapper, 'archive');
    expect(archive.attributes('disabled')).toBeDefined();
    expect(wrapper.find('[data-batch-why]').text()).toContain('翻译中 2');
    expect(archive.attributes('aria-describedby')).toBeTruthy();
    wrapper.unmount();
  });

  it('lists in the confirmation how many will be skipped and why', async () => {
    const { wrapper } = await mountPage(page([run('a'), run('b'), running('c')]));
    await wrapper.find('[data-select-page]').setValue(true);
    expect(action(wrapper, 'archive').attributes('disabled')).toBeUndefined();
    await action(wrapper, 'archive').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-batch-confirm]').exists()).toBe(true);
    expect(wrapper.find('[data-batch-skip]').text()).toContain('预计会跳过 1 个');
    expect(wrapper.find('[data-batch-skip]').text()).toContain('翻译中 1');
    wrapper.unmount();
  });

  it('Esc cancels the confirmation without doing anything and gives focus back', async () => {
    const { wrapper } = await mountPage(page([run('a')]));
    await rowBoxes(wrapper)[0].setValue(true);
    const button = action(wrapper, 'trash');
    button.element.focus();
    await button.trigger('click');
    await flushPromises();
    await wrapper.find('[data-batch-confirm]').trigger('keydown', { key: 'Escape' });
    await flushPromises();
    expect(wrapper.find('[data-batch-confirm]').exists()).toBe(false);
    expect(apiMock.batchRuns).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(button.element);
    wrapper.unmount();
  });
});

describe('running a batch', () => {
  it('shows succeeded, failed and skipped, explains the problems, and retries only the failures', async () => {
    const { wrapper } = await mountPage(page([run('a'), run('b'), run('c')]));
    await wrapper.find('[data-select-page]').setValue(true);
    apiMock.batchRuns.mockResolvedValueOnce(result('trash', [
      { id: 'a', outcome: 'succeeded' },
      { id: 'b', outcome: 'failed', reason_code: 'RUN_STILL_EXECUTING', message: '任务仍在运行，请先取消后再删除', name: '协议B' },
      { id: 'c', outcome: 'skipped', reason_code: 'ALREADY_IN_TRASH', message: '任务已在回收站中' },
    ]));
    await action(wrapper, 'trash').trigger('click');
    await flushPromises();
    await wrapper.find('[data-batch-confirm-go]').trigger('click');
    await flushPromises();
    const summary = wrapper.find('[data-batch-result]').text();
    expect(summary).toContain('成功 1 · 失败 1 · 跳过 1');
    expect(wrapper.find('[data-batch-details]').text()).toContain('协议B — 任务仍在运行');
    expect(wrapper.find('[data-batch-scope]').exists()).toBe(false); // selection is spent

    apiMock.batchRuns.mockResolvedValueOnce(result('trash', [{ id: 'b', outcome: 'succeeded' }]));
    await wrapper.find('[data-batch-retry]').trigger('click');
    await flushPromises();
    const [body, key] = apiMock.batchRuns.mock.calls[1];
    expect(body).toEqual({ action: 'trash', ids: ['b'] });
    expect(key).not.toBe(apiMock.batchRuns.mock.calls[0][1]); // a new decision, a new key
    expect(wrapper.find('[data-batch-result]').text()).toContain('成功 1 · 失败 0');
    wrapper.unmount();
  });

  it('refreshes the list afterwards', async () => {
    const { wrapper } = await mountPage(page([run('a')]));
    await rowBoxes(wrapper)[0].setValue(true);
    apiMock.batchRuns.mockResolvedValue(result('archive', [{ id: 'a', outcome: 'succeeded' }]));
    const before = apiMock.listRuns.mock.calls.length;
    await action(wrapper, 'archive').trigger('click');
    await flushPromises();
    await wrapper.find('[data-batch-confirm-go]').trigger('click');
    await flushPromises();
    expect(apiMock.listRuns.mock.calls.length).toBeGreaterThan(before);
    wrapper.unmount();
  });

  it('sends explicit ids in chunks the server accepts', async () => {
    const many = Array.from({ length: 450 }, (_, i) => run(`r${i}`));
    const { wrapper } = await mountPage(page(many.slice(0, 25), { total: 450 }));
    runList.selectedIds.value = new Set(many.map((r) => r.id));
    apiMock.batchRuns.mockImplementation(async (body) => result('archive', body.ids.map((id) => ({ id, outcome: 'succeeded' }))));
    const combined = await runList.runBatch('archive');
    expect(apiMock.batchRuns.mock.calls.map(([body]) => body.ids.length)).toEqual([200, 200, 50]);
    expect(combined.succeeded).toBe(450);
    wrapper.unmount();
  });

  it('an expired selection asks the person to select again', async () => {
    const { wrapper } = await mountPage(page([run('a')], { total: 30, next_cursor: 'c' }));
    await wrapper.find('[data-select-page]').setValue(true);
    apiMock.createRunSelection.mockResolvedValue({ selection_token: 't', count: 30, scope: 'active' });
    await wrapper.find('[data-select-all]').trigger('click');
    await flushPromises();
    apiMock.batchRuns.mockRejectedValue(Object.assign(new Error('这次选择已过期'), { status: 410 }));
    await action(wrapper, 'archive').trigger('click');
    await flushPromises();
    await wrapper.find('[data-batch-confirm-go]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-batch-error]').text()).toContain('已过期');
    expect(wrapper.find('[data-batch-scope]').exists()).toBe(false);
    expect(wrapper.find('[data-select-notice]').text()).toContain('过期');
    wrapper.unmount();
  });
});

describe('the recycle bin', () => {
  const binRow = (id, extra = {}) => run(id, {
    allowed_actions: ['restore_from_trash'], deleted_at: '2026-10-01T00:00:00Z', purge_after: '2026-10-31T00:00:00Z', trash_days_left: 12,
    ...extra,
  });

  it('asks for the bin through the archive filter and shows the days left', async () => {
    const { wrapper, router } = await mountPage(page([binRow('a')]), '/workbench?archived=trash');
    expect(apiMock.listRuns.mock.calls.at(-1)[0]).toMatchObject({ trash: 'true' });
    expect(apiMock.listRuns.mock.calls.at(-1)[0].archived).toBeUndefined();
    expect(wrapper.find('[data-trash-note]').text()).toContain('还剩 12 天');
    expect(wrapper.find('.qy-task-row [data-trash-restore]').exists()).toBe(true);
    expect(wrapper.find('.qy-task-row [data-trash-purge]').exists()).toBe(false); // not an administrator
    await wrapper.find('.qy-task-row').trigger('click');
    expect(router.currentRoute.value.path).toBe('/workbench'); // cannot open a task in the bin
    wrapper.unmount();
  });

  it('restores one task from its row', async () => {
    const { wrapper } = await mountPage(page([binRow('a')]), '/workbench?archived=trash');
    await wrapper.find('[data-trash-restore]').trigger('click');
    await flushPromises();
    expect(apiMock.restoreRunFromTrash).toHaveBeenCalledWith('a');
    wrapper.unmount();
  });

  it('shows what a half-finished purge is, and an empty bin says how long things are kept', async () => {
    const { wrapper } = await mountPage(page([binRow('a', { purge_status: 'failed', allowed_actions: ['purge'] })]), '/workbench?archived=trash');
    expect(wrapper.find('[data-trash-note]').text()).toContain('永久清除失败');
    wrapper.unmount();
    runList.reset();
    const empty = await mountPage(page([]), '/workbench?archived=trash');
    expect(empty.wrapper.find('[data-trash-empty]').text()).toContain('保留 30 天');
    empty.wrapper.unmount();
  });

  it('permanent removal needs the number of tasks typed in, and only an administrator sees it', async () => {
    const { wrapper } = await mountPage(
      page([binRow('a', { allowed_actions: ['restore_from_trash', 'purge'] }), binRow('b', { allowed_actions: ['restore_from_trash', 'purge'] })]),
      '/workbench?archived=trash',
    );
    await wrapper.find('[data-select-page]').setValue(true);
    expect(action(wrapper, 'restore_from_trash').exists() && action(wrapper, 'purge').exists()).toBe(true);
    expect(action(wrapper, 'archive').exists()).toBe(false);
    await action(wrapper, 'purge').trigger('click');
    await flushPromises();
    const go = wrapper.find('[data-batch-confirm-go]');
    expect(go.attributes('disabled')).toBeDefined();
    await wrapper.find('[data-batch-typed]').setValue('1');
    expect(go.attributes('disabled')).toBeDefined();
    await wrapper.find('[data-batch-typed]').setValue('2');
    expect(wrapper.find('[data-batch-confirm-go]').attributes('disabled')).toBeUndefined();
    apiMock.batchRuns.mockResolvedValue(result('purge', [{ id: 'a', outcome: 'succeeded' }, { id: 'b', outcome: 'succeeded' }]));
    await wrapper.find('[data-batch-confirm-go]').trigger('click');
    await flushPromises();
    expect(apiMock.batchRuns.mock.calls[0][0]).toEqual({ action: 'purge', ids: ['a', 'b'] });
    wrapper.unmount();
  });

  it('a row\'s own "permanently remove" opens the same confirmation for that one task', async () => {
    const { wrapper } = await mountPage(page([binRow('a', { allowed_actions: ['purge'] })]), '/workbench?archived=trash');
    await wrapper.find('[data-trash-purge]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-batch-confirm]').text()).toContain('永久清除 1 个任务');
    wrapper.unmount();
  });

  it('selects the bin\'s own matches, not the active ones', async () => {
    const { wrapper } = await mountPage(page([binRow('a')], { total: 40, next_cursor: 'c' }), '/workbench?archived=trash');
    await wrapper.find('[data-select-page]').setValue(true);
    apiMock.createRunSelection.mockResolvedValue({ selection_token: 't', count: 40, scope: 'trash' });
    await wrapper.find('[data-select-all]').trigger('click');
    await flushPromises();
    expect(apiMock.createRunSelection).toHaveBeenCalledWith(expect.objectContaining({ trash: true }));
    wrapper.unmount();
  });
});

describe('deleting from a row', () => {
  it('says the task goes to the bin and can be restored', async () => {
    const { wrapper } = await mountPage(page([run('a')]));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    await wrapper.findAll('.qy-task-row button').find((b) => b.text() === '删除').trigger('click');
    await flushPromises();
    expect(confirm.mock.calls[0][0]).toContain('回收站');
    expect(apiMock.deleteRun).toHaveBeenCalledWith('a');
    wrapper.unmount();
    confirm.mockRestore();
  });
});

describe('accessibility', () => {
  it('has no serious violations with a selection, the bar and the confirmation open', async () => {
    const { wrapper } = await mountPage(page([run('a'), run('b')]));
    await wrapper.find('[data-select-page]').setValue(true);
    await action(wrapper, 'trash').trigger('click');
    await flushPromises();
    const results = await axe.run(wrapper.element.ownerDocument.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
    const serious = results.violations.filter((v) => ['serious', 'critical'].includes(v.impact));
    expect(serious.map((v) => `${v.id}: ${v.nodes[0]?.html}`)).toEqual([]);
    wrapper.unmount();
  });
});

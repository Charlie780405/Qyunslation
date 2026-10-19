import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
  cancelRun: vi.fn(async () => ({})),
  patchRun: vi.fn(async () => ({})),
}));
vi.mock('../api.js', () => ({ api: apiMock }));

import WorkbenchPage from '../pages/WorkbenchPage.vue';
import { useSessionStore } from '../stores/session.js';
import { filtersFromQuery, filtersToQuery, listView, runList } from '../stores/runs.js';

function run(id, overrides = {}) {
  return {
    id, filename: `${id}.pdf`, display_name: null, name_version: 0, generation: 1, version_count: 1,
    source_language: 'English', target_language: '简体中文',
    status: 'failed', stage: 'qa', quality_state: 'draft', progress: null, artifacts: [],
    lifecycle: 'failed', allowed_actions: ['open', 'rename', 'archive', 'delete', 'retry'],
    qa_summary: {}, formal_gate: { passed: false }, ...overrides,
  };
}

function page(items, extra = {}) {
  return { items, next_cursor: null, total: items.length, facets: { lifecycle: {}, total: items.length }, ...extra };
}

async function mountPage(first, path = '/workbench') {
  if (first) apiMock.listRuns.mockResolvedValue(first); // null: the caller already set up the mock
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

beforeEach(() => {
  runList.reset();
  listView.openedId = '';
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
  vi.clearAllMocks();
});

const lastParams = () => apiMock.listRuns.mock.calls.at(-1)[0];

describe('filters and the URL', () => {
  it('round-trips only the non-default filters', () => {
    const filters = filtersFromQuery({ q: '方案', lifecycle: 'failed,review', archived: 'all' });
    expect(filters).toMatchObject({ q: '方案', lifecycle: ['failed', 'review'], archived: 'all', sort: 'created' });
    expect(filtersToQuery(filters)).toEqual({ q: '方案', lifecycle: 'failed,review', archived: 'all' });
    expect(filtersToQuery(filtersFromQuery({}))).toEqual({});
  });
});

describe('searching and filtering', () => {
  it('debounces typing into one server request and writes it to the URL', async () => {
    const { wrapper, router } = await mountPage(page([run('r1')]));
    const before = apiMock.listRuns.mock.calls.length;
    const input = wrapper.find('[data-run-search]');
    await input.setValue('协');
    await input.setValue('协议');
    await vi.advanceTimersByTimeAsync(200);
    expect(apiMock.listRuns.mock.calls.length).toBe(before);
    await vi.advanceTimersByTimeAsync(200);
    await flushPromises();
    expect(apiMock.listRuns.mock.calls.length).toBe(before + 1);
    expect(lastParams()).toMatchObject({ q: '协议', page_size: 25 });
    expect(router.currentRoute.value.query.q).toBe('协议');
    wrapper.unmount();
  });

  it('starts from the filters in the URL', async () => {
    const { wrapper } = await mountPage(page([run('r1')]), '/workbench?lifecycle=failed&q=abc&archived=all');
    expect(lastParams()).toMatchObject({ q: 'abc', lifecycle: 'failed', archived: 'all' });
    expect(wrapper.find('[data-run-search]').element.value).toBe('abc');
    wrapper.unmount();
  });

  it('a lifecycle chip filters on the server and shows its count', async () => {
    const { wrapper } = await mountPage(page([run('r1')], { facets: { lifecycle: { failed: 3 }, total: 3 } }));
    const chip = wrapper.find('[data-lifecycle-chip="failed"]');
    expect(chip.text()).toContain('3');
    await chip.trigger('click');
    await flushPromises();
    expect(lastParams().lifecycle).toBe('failed');
    expect(wrapper.find('[data-lifecycle-chip="failed"]').attributes('aria-pressed')).toBe('true');
    wrapper.unmount();
  });

  it('shows a no-match state with a way out, which is different from the empty state', async () => {
    const { wrapper } = await mountPage(page([]), '/workbench?q=zzz');
    expect(wrapper.find('[data-run-nomatch]').exists()).toBe(true);
    expect(wrapper.find('[data-run-empty]').exists()).toBe(false);
    apiMock.listRuns.mockResolvedValue(page([run('r1')]));
    await wrapper.find('[data-run-nomatch] button').trigger('click');
    await flushPromises();
    expect(lastParams().q).toBeUndefined();
    expect(wrapper.find('.qy-task-row').exists()).toBe(true);
    wrapper.unmount();
  });

  it('shows the empty state only when there is nothing at all', async () => {
    const { wrapper } = await mountPage(page([]));
    expect(wrapper.find('[data-run-empty]').exists()).toBe(true);
    expect(wrapper.find('[data-run-nomatch]').exists()).toBe(false);
    wrapper.unmount();
  });
});

describe('paging and failure', () => {
  it('loads the next page with the cursor and appends without duplicates', async () => {
    const { wrapper } = await mountPage(page([run('r1'), run('r2')], { next_cursor: 'c1', total: 3 }));
    expect(wrapper.find('[data-run-more]').text()).toContain('已显示 2 / 共 3');
    apiMock.listRuns.mockResolvedValue(page([run('r2'), run('r3')], { total: 3 }));
    await wrapper.find('[data-run-more] button').trigger('click');
    await flushPromises();
    expect(lastParams()).toMatchObject({ cursor: 'c1' });
    expect(wrapper.findAll('.qy-task-row')).toHaveLength(3);
    expect(wrapper.find('[data-run-more]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('keeps the rows on screen and offers a retry when a refresh fails', async () => {
    const { wrapper } = await mountPage(page([run('r1')]));
    apiMock.listRuns.mockRejectedValue(new Error('服务暂时不可用'));
    await wrapper.findAll('.qy-task-toolbar button').find((b) => b.text() === '刷新').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-run-stale]').text()).toContain('服务暂时不可用');
    expect(wrapper.findAll('.qy-task-row')).toHaveLength(1);
    wrapper.unmount();
  });

  it('shows an error state with retry when the first load fails', async () => {
    apiMock.listRuns.mockRejectedValue(new Error('boom'));
    const { wrapper } = await mountPage(null);
    expect(wrapper.find('[data-run-error]').exists()).toBe(true);
    apiMock.listRuns.mockResolvedValue(page([run('r1')]));
    await wrapper.find('[data-run-error] button').trigger('click');
    await flushPromises();
    expect(wrapper.find('.qy-task-row').exists()).toBe(true);
    wrapper.unmount();
  });
});

describe('versions', () => {
  it('shows which version a row is and how many there are', async () => {
    const { wrapper } = await mountPage(page([run('r1', { generation: 2, version_count: 3 })]));
    expect(wrapper.find('[data-run-version]').text()).toContain('v2/共 3 版');
    wrapper.unmount();
  });
});

describe('inline rename', () => {
  async function startRename(wrapper) {
    await wrapper.findAll('.qy-task-row button').find((b) => b.text() === '重命名').trigger('click');
    await flushPromises();
    return wrapper.find('[data-rename-input]');
  }

  it('saves on Enter with the name version and updates the row without a reload', async () => {
    const { wrapper } = await mountPage(page([run('r1', { name_version: 4 })]));
    apiMock.patchRun.mockResolvedValue({ display_name: '新名字', name_version: 5 });
    const input = await startRename(wrapper);
    await input.setValue('  新名字 ');
    const before = apiMock.listRuns.mock.calls.length;
    await input.trigger('keydown', { key: 'Enter' });
    await flushPromises();
    expect(apiMock.patchRun).toHaveBeenCalledWith('r1', { display_name: '新名字' }, { nameVersion: 4 });
    expect(wrapper.find('.qy-task-row').text()).toContain('新名字');
    expect(wrapper.find('[data-rename-input]').exists()).toBe(false);
    expect(apiMock.listRuns.mock.calls.length).toBe(before);
    wrapper.unmount();
  });

  it('Esc cancels without saving and returns focus to the row', async () => {
    const { wrapper } = await mountPage(page([run('r1')]));
    const input = await startRename(wrapper);
    await input.setValue('不会保存');
    await input.trigger('keydown', { key: 'Escape' });
    await flushPromises();
    expect(apiMock.patchRun).not.toHaveBeenCalled();
    expect(wrapper.find('[data-rename-input]').exists()).toBe(false);
    expect(document.activeElement?.getAttribute('data-run-id')).toBe('r1');
    wrapper.unmount();
  });

  it('refuses an empty name locally and offers the explicit way back to the file name', async () => {
    const { wrapper } = await mountPage(page([run('r1', { display_name: '自定义' })]));
    const input = await startRename(wrapper);
    await input.setValue('   ');
    await wrapper.find('[data-rename-save]').trigger('click');
    await flushPromises();
    expect(apiMock.patchRun).not.toHaveBeenCalled();
    expect(wrapper.find('[data-rename-error]').text()).toContain('不能为空');
    apiMock.patchRun.mockResolvedValue({ display_name: null, name_version: 1 });
    await wrapper.find('[data-rename-reset]').trigger('click');
    await flushPromises();
    expect(apiMock.patchRun).toHaveBeenCalledWith('r1', { reset_display_name: true }, { nameVersion: 0 });
    wrapper.unmount();
  });

  it('shows the other tab\'s name on a conflict and saves over it only on a second, explicit save', async () => {
    const { wrapper } = await mountPage(page([run('r1', { display_name: '旧', name_version: 1 })]));
    const conflict = Object.assign(new Error('该任务的名称已在其他页面被修改'), {
      status: 409,
      payload: { detail: { code: 'NAME_CONFLICT', current_name: '别人改的', current_version: 2 } },
    });
    apiMock.patchRun.mockRejectedValueOnce(conflict);
    const input = await startRename(wrapper);
    await input.setValue('我改的');
    await input.trigger('keydown', { key: 'Enter' });
    await flushPromises();
    expect(wrapper.find('[data-rename-error]').text()).toContain('别人改的');
    expect(wrapper.find('[data-rename-input]').element.value).toBe('我改的');
    apiMock.patchRun.mockResolvedValue({ display_name: '我改的', name_version: 3 });
    await wrapper.find('[data-rename-save]').trigger('click');
    await flushPromises();
    expect(apiMock.patchRun).toHaveBeenLastCalledWith('r1', { display_name: '我改的' }, { nameVersion: 2 });
    wrapper.unmount();
  });
});

describe('coming back from a task', () => {
  it('remembers where the person was', async () => {
    const { wrapper, router } = await mountPage(page([run('r1'), run('r2')]));
    window.scrollY = 120;
    await wrapper.findAll('.qy-task-row')[1].trigger('click');
    await flushPromises();
    expect(listView).toMatchObject({ openedId: 'r2', scrollY: 120 });
    expect(router.currentRoute.value.path).toBe('/workbench/r2');
    wrapper.unmount();
  });
});

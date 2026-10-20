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
  cancelRun: vi.fn(async () => ({})),
  patchRun: vi.fn(async () => ({})),
}));
vi.mock('../api.js', () => ({ api: apiMock }));

import WorkbenchPage from '../pages/WorkbenchPage.vue';
import { useSessionStore } from '../stores/session.js';

function run(overrides) {
  return {
    id: 'r1', filename: 'protocol.pdf', source_language: 'English', target_language: '简体中文',
    status: 'gated', stage: 'qa', quality_state: 'qa_blocked', progress: null, artifacts: [],
    lifecycle: 'qa_action', allowed_actions: ['open', 'rename', 'archive', 'delete', 'retry', 'discard', 'requalify', 'open_qa'],
    pending_counts: { qa_blockers: 4, qa_unavailable: 0, unresolved_terms: 0, unconfirmed_affiliations: 0 },
    qa_summary: { blocker: 4 }, formal_gate: { passed: false }, ...overrides,
  };
}

async function mountWith(items) {
  apiMock.listRuns.mockResolvedValue({ items });
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
  return { wrapper, router };
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.clearAllMocks();
});

const buttons = (wrapper) => wrapper.findAll('.qy-task-row button').map((b) => b.text());

describe('task list follows the server lifecycle', () => {
  it('a run waiting at QA is not shown as translating and has no progress or cancel', async () => {
    const { wrapper } = await mountWith([run({})]);
    const row = wrapper.find('.qy-task-row');
    expect(row.text()).toContain('待处理质量问题');
    expect(row.text()).not.toContain('翻译中');
    expect(row.find('[role="progressbar"]').exists()).toBe(false);
    expect(wrapper.find('[data-active-run-hint]').exists()).toBe(false);
    expect(buttons(wrapper)).not.toContain('取消');
    expect(buttons(wrapper)).toContain('归档');
    expect(buttons(wrapper)).toContain('删除');
    wrapper.unmount();
  });

  it('offers one click into the quality issues with the pending count', async () => {
    const { wrapper, router } = await mountWith([run({})]);
    const entry = wrapper.findAll('.qy-task-row button').find((b) => b.text().includes('处理质量问题'));
    expect(entry.text()).toContain('（4）');
    await entry.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.path).toBe('/workbench/r1');
    expect(router.currentRoute.value.query.tab).toBe('qa');
    wrapper.unmount();
  });

  it('an executing run keeps progress and cancel on the task card only', async () => {
    const { wrapper } = await mountWith([run({
      status: 'translating', stage: 'text', quality_state: 'draft', progress: 40, lifecycle: 'executing',
      allowed_actions: ['open', 'rename', 'cancel'], pending_counts: {},
    })]);
    expect(wrapper.find('[data-active-run-hint]').exists()).toBe(true);
    expect(wrapper.find('[data-active-run-hint]').text()).toContain('1 个任务进行中');
    expect(wrapper.findAll('[role="progressbar"]')).toHaveLength(1);
    expect(wrapper.find('.qy-task-row [role="progressbar"]').exists()).toBe(true);
    expect(buttons(wrapper)).toContain('取消');
    expect(buttons(wrapper)).not.toContain('归档');
    wrapper.unmount();
  });

  it('a QA-blocked run does not take over the active-run hint from a real one', async () => {
    const { wrapper } = await mountWith([
      run({ id: 'blocked' }),
      run({ id: 'live', status: 'translating', stage: 'text', quality_state: 'draft', progress: 10, lifecycle: 'executing', allowed_actions: ['open', 'cancel'], pending_counts: {} }),
    ]);
    expect(wrapper.find('[data-active-run-hint]').text()).toContain('查看进度');
    expect(wrapper.find('.qy-task-row[data-run-id="live"]').text()).toContain('10%');
    wrapper.unmount();
  });

  it('shows the QA-unavailable and changes-requested phases in plain Chinese', async () => {
    const { wrapper } = await mountWith([
      run({ id: 'u', lifecycle: 'qa_unavailable', quality_state: 'qa_unavailable', pending_counts: { qa_unavailable: 1 } }),
      run({ id: 'c', lifecycle: 'changes_requested', quality_state: 'changes_requested', pending_counts: {} }),
    ]);
    const text = wrapper.text();
    expect(text).toContain('质量检查未完成');
    expect(text).toContain('已退回修改');
    expect(text).not.toMatch(/qa_unavailable|changes_requested|qa_blocked/);
    wrapper.unmount();
  });

  it('an interrupted run can be resumed, archived and deleted', async () => {
    const { wrapper } = await mountWith([run({
      status: 'interrupted', lifecycle: 'interrupted', quality_state: 'draft',
      allowed_actions: ['open', 'rename', 'resume', 'archive', 'delete', 'retry'], pending_counts: {},
    })]);
    expect(buttons(wrapper)).toEqual(expect.arrayContaining(['续跑', '归档', '删除']));
    wrapper.unmount();
  });

  it('puts a todo bar above everything that counts what needs a person', async () => {
    const { wrapper, router } = await mountWith([
      run({ id: 'a' }),
      run({ id: 'b', lifecycle: 'qa_unavailable', quality_state: 'qa_unavailable', pending_counts: { qa_unavailable: 1 } }),
      run({ id: 'c', lifecycle: 'review', quality_state: 'review_ready', pending_counts: {}, formal_gate: { passed: true } }),
      run({ id: 'd', status: 'succeeded', lifecycle: 'completed', quality_state: 'approved', pending_counts: {} }),
    ]);
    const bar = wrapper.find('[data-todo-bar]');
    expect(bar.exists()).toBe(true);
    expect(bar.text()).toContain('2 个任务需要处理质量问题');
    expect(bar.text()).toContain('1 个待人工复核');
    await bar.find('button').trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.path).toBe('/workbench/a');
    expect(router.currentRoute.value.query.tab).toBe('qa');
    wrapper.unmount();
  });

  it('shows no todo bar when nothing needs attention', async () => {
    const { wrapper } = await mountWith([
      run({ id: 'd', status: 'succeeded', lifecycle: 'completed', quality_state: 'approved', pending_counts: {} }),
    ]);
    expect(wrapper.find('[data-todo-bar]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('does not claim "not started" while a file is waiting for its pre-check', async () => {
    const { wrapper } = await mountWith([]);
    expect(wrapper.find('.qy-upload-panel .qy-panel-status').text()).toBe('等待选择文件');
    const input = wrapper.find('#workbench-file');
    Object.defineProperty(input.element, 'files', { value: [new File(['x'], 'a.pdf')], configurable: true });
    await input.trigger('change');
    expect(wrapper.find('.qy-upload-panel .qy-panel-status').text()).toBe('待预检');
    wrapper.unmount();
  });
});

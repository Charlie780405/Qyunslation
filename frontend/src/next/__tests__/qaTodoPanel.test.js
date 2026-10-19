import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia } from 'pinia';
import axe from 'axe-core';

const apiMock = vi.hoisted(() => ({
  getRun: vi.fn(),
  getRunEvents: vi.fn(),
  getQaItems: vi.fn(),
  postReviewDecision: vi.fn(),
  listRunTermCandidates: vi.fn(),
  listRunAffiliationSegments: vi.fn(),
  getReviewDraft: vi.fn(),
  saveReviewDraft: vi.fn(),
  requalifyRun: vi.fn(),
  cancelRun: vi.fn(),
  resumeRun: vi.fn(),
  retryRun: vi.fn(),
  postQaDisposition: vi.fn(),
  postQaDispositionsBatch: vi.fn(),
  createRevision: vi.fn(),
  listModelProfiles: vi.fn(),
  previewUrl: (id, side) => `/api/v1/translation-runs/${id}/preview/${side}`,
}));
vi.mock('../api.js', () => ({ api: apiMock }));
vi.mock('../lib/pdfjs.js', () => ({
  loadPdfjs: async () => ({
    getDocument: () => ({
      promise: Promise.resolve({
        numPages: 5,
        getPage: async () => ({
          getViewport: ({ scale }) => ({ width: 600 * scale, height: 800 * scale }),
          render: () => ({ promise: Promise.resolve(), cancel() {} }),
        }),
        destroy: async () => {},
      }),
    }),
  }),
}));

import RunDetailPage from '../pages/RunDetailPage.vue';

const REASON = '已逐项核对原文，确认属于版式差异';

function item(overrides) {
  return {
    id: 'i1', category: 'ad', severity: 'blocker', code: 'AD_NUMBER_DRIFT', message: '保护性数字发生变化',
    object_id: null, resolved: false, evidence: { missing_in_target: ['45.2%'] },
    title: '数字、剂量或统计量与原文不一致', why: '剂量、百分比等数值改变会改变临床含义。',
    how: '对照原文位置核对译文，修正后重新翻译。', rule_class: 'C1', status: 'open', batchable: false,
    is_current: true, round_id: 'rd1', previous_disposition: false, prior_version_disposition: null,
    disposition: null, history: [], allowed_dispositions: ['report_false_positive'],
    location: { anchors: [{ side: 'source', page: 3, label: '45.2%', excerpt: '…45.2% improved at week 16…' }] },
    ...overrides,
  };
}

const ITEMS = [
  item({}),
  item({ id: 'i2', code: 'LOGO_MISSING', rule_class: 'C2', title: '原文首页图片未在译文中保留', why: '标识缺失可能让文件失效。',
    how: '查看首页，必要时由复核人授权例外。', message: '首页图片未保留',
    location: { anchors: [], unlocatable_reason: '页数差异不属于某一页' }, allowed_dispositions: ['report_false_positive', 'grant_waiver'] }),
  item({ id: 'i3', severity: 'warning', code: 'LATIN_RESIDUE', rule_class: 'W', title: '译文中英文残留较多', batchable: true,
    why: '可能有未翻译的段落。', how: '确认后可标记已阅。', allowed_dispositions: ['acknowledge', 'report_false_positive'],
    location: { anchors: [{ side: 'translated', page: 2, label: '英文残留', excerpt: 'Subjects receiving treatment…' }] } }),
  item({ id: 'i4', severity: 'warning', code: 'LATIN_RESIDUE', rule_class: 'W', title: '译文中英文残留较多', batchable: true,
    why: '可能有未翻译的段落。', how: '确认后可标记已阅。', allowed_dispositions: ['acknowledge', 'report_false_positive'],
    location: { anchors: [{ side: 'translated', page: 4, label: '英文残留' }] } }),
  item({ id: 'i5', code: 'LOGO_MISSING', rule_class: 'C2', title: '原文首页图片未在译文中保留', status: 'waived', resolved: true,
    allowed_dispositions: ['revoke_waiver'], disposition: { action: 'grant_waiver', actor_sub: 'rev', reason: '印章位置不同', self_review: false },
    history: [{ id: 'd1', action: 'grant_waiver', actor_sub: 'rev', actor_role: 'reviewer', reason: '印章位置不同', self_review: false, created_at: '2026-10-19T08:00:00Z' }] }),
];

const RUN = {
  id: 'run-1', filename: 'a.pdf', status: 'gated', stage: 'qa', quality_state: 'qa_blocked',
  lifecycle: 'qa_action', next_action: 'fix_quality_issues', superseded_by: null,
  allowed_actions: ['open', 'rename', 'archive', 'delete', 'retry', 'revise', 'discard', 'requalify', 'open_qa'],
  pending_counts: { qa_blockers: 2, qa_unavailable: 0, unresolved_terms: 1, unconfirmed_affiliations: 0 },
  qa_summary: { blocker: 3, open_blocker: 2, waived: 1 },
  formal_gate: { passed: false, reasons: ['qa_blockers', 'unresolved_terms'], qa_blockers: 2 },
  qa_check: { round_no: 2, status: 'succeeded', diff: { baseline: 'previous_round', new: 1, resolved: 2, persisting: 3 }, rule_set_version: 'qa-abc123' },
};

async function mountPage(url = '/workbench/run-1') {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, headers: { get: () => 'application/pdf' },
    arrayBuffer: async () => new ArrayBuffer(8), blob: async () => new Blob(['x']),
  })));
  const router = createRouter({
    history: createMemoryHistory('/next'),
    routes: [
      { path: '/workbench', component: { template: '<div />' } },
      { path: '/termbase', component: { template: '<div />' } },
      { path: '/settings', component: { template: '<div />' } },
      { path: '/workbench/:runId', name: 'workbench-run', component: RunDetailPage, props: true },
    ],
  });
  router.push(url);
  await router.isReady();
  const wrapper = mount(RunDetailPage, { props: { runId: 'run-1' }, attachTo: document.body, global: { plugins: [router, createPinia()] } });
  await flushPromises();
  return { wrapper, router };
}

const panel = (wrapper) => wrapper.find('[data-qa-panel]');
const cards = (wrapper) => wrapper.findAll('[data-qa-panel] .qy-qa-item');
const byText = (root, text) => root.findAll('button').find((b) => b.text().includes(text));
// Selecting writes ?obj= with router.replace, which settles asynchronously.
async function pick(wrapper, index) {
  await cards(wrapper)[index].trigger('click');
  await flushPromises();
}

beforeEach(() => {
  HTMLCanvasElement.prototype.getContext = () => ({});
  apiMock.getRun.mockResolvedValue(RUN);
  apiMock.getRunEvents.mockResolvedValue({ items: [] });
  apiMock.getQaItems.mockResolvedValue({ items: ITEMS });
  apiMock.getReviewDraft.mockResolvedValue({ comment: '' });
  apiMock.listRunTermCandidates.mockResolvedValue({ items: [], total: 0, unresolved: 0, page: 1, page_size: 40, rules: {} });
  apiMock.listRunAffiliationSegments.mockResolvedValue({ items: [], unconfirmed: 0 });
  apiMock.postQaDisposition.mockResolvedValue({});
  apiMock.postQaDispositionsBatch.mockResolvedValue({ results: [] });
  apiMock.createRevision.mockResolvedValue({ id: 'run-2' });
  apiMock.resumeRun.mockResolvedValue({});
  apiMock.listModelProfiles.mockResolvedValue({ items: [{ profile_id: 'internal-qwen-quality', label: '内网 Qwen 质量档', role: 'translator', provider: 'ollama', configured: true }] });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  document.body.innerHTML = '';
});

describe('QA todo panel', () => {
  it('opens on the first screen with the next step and a delivery checklist', async () => {
    const { wrapper } = await mountPage();
    const text = panel(wrapper).text();
    expect(text).toContain('下一步');
    expect(text).toContain('2 个阻断问题');
    const checklist = panel(wrapper).find('[aria-label="交付清单"]').text();
    expect(checklist).toContain('阻断问题');
    expect(checklist).toMatch(/2/);
    expect(checklist).toContain('待审核术语');
    expect(checklist).toContain('正式稿');
    expect(checklist).toContain('未解锁');
    expect(panel(wrapper).text()).toContain('第 2 轮检查');
    expect(panel(wrapper).text()).toContain('新增 1');
    expect(panel(wrapper).text()).toContain('已解决 2');
    wrapper.unmount();
  });

  it('lists open problems blockers first and hides handled ones until asked', async () => {
    const { wrapper } = await mountPage();
    expect(cards(wrapper)).toHaveLength(4); // waived item is hidden under "未处理"
    expect(cards(wrapper)[0].text()).toContain('数字、剂量或统计量与原文不一致');
    await byText(panel(wrapper), '已处理').trigger('click');
    expect(cards(wrapper)).toHaveLength(1);
    expect(cards(wrapper)[0].text()).toContain('已授权例外');
    await byText(panel(wrapper), '全部').trigger('click');
    expect(cards(wrapper)).toHaveLength(5);
    wrapper.unmount();
  });

  it('explains where, why and how for the selected problem', async () => {
    const { wrapper } = await mountPage();
    await pick(wrapper, 0);
    const detail = panel(wrapper).find('[data-qa-detail]').text();
    expect(detail).toContain('哪里有问题');
    expect(detail).toContain('原文第 3 页');
    expect(detail).toContain('45.2% improved at week 16');
    expect(detail).toContain('为什么影响交付');
    expect(detail).toContain('剂量、百分比等数值改变会改变临床含义');
    expect(detail).toContain('怎么处理');
    expect(detail).toContain('对照原文位置核对译文');
    expect(detail).not.toMatch(/\bAD_NUMBER_DRIFT\b.*\bblocker\b/);
    wrapper.unmount();
  });

  it('says honestly when a problem has no place in the document', async () => {
    const { wrapper } = await mountPage();
    await pick(wrapper, 1);
    expect(panel(wrapper).find('[data-qa-detail]').text()).toContain('页数差异不属于某一页');
    wrapper.unmount();
  });

  it('jumps the side-by-side view to the page of the problem', async () => {
    const { wrapper, router } = await mountPage();
    await pick(wrapper, 0);
    await byText(panel(wrapper), '在对照视图定位').trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.query.page).toBe('3');
    wrapper.unmount();
  });

  it('offers a critical fact no way to be waved through', async () => {
    const { wrapper } = await mountPage();
    await pick(wrapper, 0);
    const actions = panel(wrapper).find('[data-qa-actions]');
    expect(actions.text()).toContain('反馈误报');
    expect(actions.text()).not.toContain('授权例外');
    expect(actions.text()).not.toContain('确认已阅');
    expect(panel(wrapper).find('[data-qa-detail]').text()).toContain('不能直接放行');
    wrapper.unmount();
  });

  it('records a waiver only with a reason and shows success', async () => {
    const { wrapper } = await mountPage();
    await pick(wrapper, 1);
    await byText(panel(wrapper).find('[data-qa-actions]'), '授权例外').trigger('click');
    const submit = byText(panel(wrapper).find('[data-qa-form]'), '提交');
    expect(submit.attributes('disabled')).toBeDefined(); // no reason yet
    await panel(wrapper).find('[data-qa-form] textarea').setValue('短');
    expect(byText(panel(wrapper).find('[data-qa-form]'), '提交').attributes('disabled')).toBeDefined();
    await panel(wrapper).find('[data-qa-form] textarea').setValue(REASON);
    await byText(panel(wrapper).find('[data-qa-form]'), '提交').trigger('click');
    await flushPromises();
    expect(apiMock.postQaDisposition).toHaveBeenCalledWith('run-1', 'i2', {
      action: 'grant_waiver', reason: REASON, expected_round_id: 'rd1',
    });
    expect(wrapper.text()).toContain('已记录');
    wrapper.unmount();
  });

  it('shows why a disposition was refused and keeps the form open for another try', async () => {
    apiMock.postQaDisposition.mockRejectedValueOnce(new Error('误报需要由反馈人以外的人确认'));
    const { wrapper } = await mountPage();
    await pick(wrapper, 0);
    await byText(panel(wrapper).find('[data-qa-actions]'), '反馈误报').trigger('click');
    await panel(wrapper).find('[data-qa-form] textarea').setValue(REASON);
    await byText(panel(wrapper).find('[data-qa-form]'), '提交').trigger('click');
    await flushPromises();
    expect(panel(wrapper).find('[role="alert"]').text()).toContain('误报需要由反馈人以外的人确认');
    expect(panel(wrapper).find('[data-qa-form] textarea').element.value).toBe(REASON);
    wrapper.unmount();
  });

  it('batch handling starts with nothing selected and sends only what was chosen', async () => {
    apiMock.postQaDispositionsBatch.mockResolvedValue({
      results: [{ item_id: 'i3', outcome: 'succeeded' }],
    });
    const { wrapper } = await mountPage();
    await byText(panel(wrapper), '批量处理').trigger('click');
    const boxes = panel(wrapper).findAll('[data-qa-batch] input[type="checkbox"]');
    expect(boxes).toHaveLength(2);
    expect(boxes.every((b) => !b.element.checked)).toBe(true);
    const submit = () => byText(panel(wrapper).find('[data-qa-batch]'), '提交');
    expect(submit().attributes('disabled')).toBeDefined();
    await boxes[0].setValue(true);
    await panel(wrapper).find('[data-qa-batch] textarea').setValue('已确认这些英文是缩写和药名，无需翻译');
    await submit().trigger('click');
    await flushPromises();
    expect(apiMock.postQaDispositionsBatch).toHaveBeenCalledWith('run-1', {
      action: 'acknowledge', reason: '已确认这些英文是缩写和药名，无需翻译', item_ids: ['i3'],
    });
    wrapper.unmount();
  });

  it('never offers batch handling for critical facts', async () => {
    apiMock.getQaItems.mockResolvedValue({ items: [item({}), item({ id: 'x2' })] });
    const { wrapper } = await mountPage();
    expect(byText(panel(wrapper), '批量处理')).toBeUndefined();
    wrapper.unmount();
  });

  it('asks for confirmation before creating a revision, then opens it on its quality todo', async () => {
    const { wrapper, router } = await mountPage();
    await byText(panel(wrapper), '生成修订版').trigger('click');
    await flushPromises();
    const dialog = document.body.querySelector('[data-run-confirm]');
    expect(dialog).not.toBeNull();
    expect(apiMock.createRevision).not.toHaveBeenCalled(); // nothing starts before the person confirms
    expect(dialog.textContent).toContain('冻结');
    [...dialog.querySelectorAll('button')].find((b) => b.textContent.includes('确认并生成修订版')).click();
    await flushPromises();
    expect(apiMock.createRevision).toHaveBeenCalledWith('run-1', {});
    expect(router.currentRoute.value.path).toBe('/workbench/run-2');
    expect(router.currentRoute.value.query.tab).toBe('qa');
    wrapper.unmount();
  });

  it('resuming an interrupted task confirms the frozen configuration first', async () => {
    apiMock.getRun.mockResolvedValue({ ...RUN, status: 'interrupted', lifecycle: 'interrupted', quality_state: 'draft', allowed_actions: ['open', 'resume', 'retry', 'archive', 'delete'] });
    apiMock.getQaItems.mockResolvedValue({ items: [] });
    const { wrapper } = await mountPage();
    await byText(wrapper, '从断点续跑').trigger('click');
    await flushPromises();
    expect(apiMock.resumeRun).not.toHaveBeenCalled();
    const dialog = document.body.querySelector('[data-run-confirm]');
    [...dialog.querySelectorAll('button')].find((b) => b.textContent.includes('按原配置续跑')).click();
    await flushPromises();
    expect(apiMock.resumeRun).toHaveBeenCalledWith('run-1');
    wrapper.unmount();
  });

  it('points out an exception granted for the previous version without inheriting it', async () => {
    apiMock.getQaItems.mockResolvedValue({
      items: [item({ id: 'p1', code: 'LOGO_MISSING', rule_class: 'C2', title: '原文首页图片未在译文中保留',
        prior_version_disposition: { action: 'grant_waiver', actor_sub: 'rev', reason: '印章位置不同', created_at: '2026-10-18T08:00:00Z' } })],
    });
    const { wrapper } = await mountPage();
    await pick(wrapper, 0);
    expect(panel(wrapper).find('[data-qa-detail]').text()).toContain('上一版本曾授权例外');
    wrapper.unmount();
  });

  it('a link with item= opens that problem', async () => {
    const { wrapper, router } = await mountPage('/workbench/run-1?tab=qa&item=i2');
    expect(panel(wrapper).find('[data-qa-detail]').text()).toContain('原文首页图片未在译文中保留');
    expect(router.currentRoute.value.query.obj).toBe('qa:i2');
    wrapper.unmount();
  });

  it('marks previews of unapproved output as not formal', async () => {
    const { wrapper } = await mountPage();
    expect(wrapper.text()).toContain('译文预览（非正式）');
    wrapper.unmount();
  });

  it('keeps the panel free of serious accessibility violations', async () => {
    const { wrapper } = await mountPage();
    await pick(wrapper, 0);
    const results = await axe.run(panel(wrapper).element, { rules: { 'color-contrast': { enabled: false } } });
    expect(results.violations.filter((v) => ['serious', 'critical'].includes(v.impact))).toEqual([]);
    wrapper.unmount();
  });
});

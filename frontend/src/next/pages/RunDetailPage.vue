<template>
  <AppShell class="qy-run-detail-shell">
    <div class="qy-run-detail">
      <header class="qy-panel qy-run-detail-head">
        <div>
          <router-link class="qy-link-button" to="/workbench">← 任务列表</router-link>
          <h1>{{ run?.display_name || run?.filename || '任务详情' }}</h1>
          <p>
            <strong class="qy-lifecycle" :data-lifecycle="lifecycleOf(run)">{{ run ? lifecycleLabel(run) : '…' }}</strong> ·
            阶段 {{ run ? stageLabel(run.stage) : '…' }} ·
            质量 {{ qualityLabel(run?.quality_state) }}
            <span v-if="run?.domain_profile === 'ad'" class="qy-badge qy-ad-badge">AD 专业模式</span>
            <span v-if="run?.quality_state === 'legacy_unverified'" class="qy-badge">旧版未验证</span>
            <span v-if="run?.quality_state === 'qa_degraded'" class="qy-badge qy-status-badge is-pending">语义 QA 降级</span>
          </p>
          <p v-if="run?.prompt_snapshot" class="qy-prompt-provenance">
            提示词 {{ run.prompt_snapshot.version }} · {{ run.prompt_snapshot.profile_id }} · {{ run.prompt_snapshot.digest?.slice(0, 19) }}…
          </p>
        </div>
        <div class="qy-run-detail-actions">
          <label v-if="run?.quality_state === 'review_ready'" class="qy-review-comment">
            <span>审核意见</span>
            <textarea v-model="reviewComment" rows="3" placeholder="记录复核意见，刷新后会自动恢复" @input="scheduleDraftSave" />
            <small v-if="draftError" class="qy-field-error" role="status" data-draft-error>{{ draftError }}</small>
          </label>
          <button
            v-if="run?.quality_state === 'review_ready'"
            class="qy-primary-button"
            type="button"
            data-action="formal-approve"
            :disabled="run?.formal_gate?.passed === false"
            :title="formalGateMessage"
            @click="approve"
          >批准正式产物</button>
          <button
            v-if="run?.quality_state === 'review_ready'"
            class="qy-secondary-button"
            type="button"
            :disabled="Boolean(busyAction)"
            @click="requestChanges"
          >请求修改</button>
          <button
            v-if="can(run, 'requalify') && ['qa_action', 'qa_unavailable'].includes(lifecycleOf(run))"
            class="qy-primary-button"
            type="button"
            :disabled="Boolean(busyAction)"
            :aria-busy="busyAction === 'requalify'"
            @click="requalify"
          >{{ busyAction === 'requalify' ? '正在检查…' : '重新检查' }}</button>
          <button
            v-if="can(run, 'resume') && run?.status === 'interrupted'"
            class="qy-primary-button"
            type="button"
            :disabled="Boolean(busyAction)"
            @click="resumeRun"
          >从断点续跑</button>
          <button
            v-if="can(run, 'discard')"
            class="qy-secondary-button"
            type="button"
            :disabled="Boolean(busyAction)"
            @click="discardRun"
          >放弃本版本</button>
          <button
            v-if="run?.quality_state === 'legacy_unverified'"
            class="qy-secondary-button"
            type="button"
            :disabled="Boolean(busyAction)"
            @click="retryV2"
          >使用新版流水线重试</button>
          <a
            v-if="sourcePreviewUrl"
            class="qy-link-button"
            :href="sourcePreviewUrl"
            target="_blank"
            rel="noopener"
          >源文件预览</a>
          <a
            v-if="translatedPreviewUrl"
            class="qy-link-button"
            :href="translatedPreviewUrl"
            target="_blank"
            rel="noopener"
          >{{ run?.quality_state === 'approved' ? '译文预览' : '译文预览（非正式）' }}</a>
        </div>
      </header>

      <section v-if="lifecycleBanner" class="qy-panel qy-lifecycle-banner" :data-lifecycle="lifecycleOf(run)" aria-live="polite">
        <strong>{{ lifecycleBanner.title }}</strong>
        <p>{{ lifecycleBanner.body }}</p>
      </section>
      <p v-if="actionNotice" class="qy-panel qy-run-detail-notice" role="status">{{ actionNotice }}</p>
      <p v-if="loadError" class="qy-panel qy-run-detail-error" role="alert">
        {{ loadError }}
        <button type="button" class="qy-secondary-button" aria-label="重新加载任务详情" @click="refresh">重试</button>
      </p>
      <p v-if="reviewError" class="qy-panel qy-run-detail-error" role="alert">{{ reviewError }}</p>
      <p v-if="softIssueText" class="qy-panel qy-run-detail-notice" role="status" data-soft-issue>{{ softIssueText }}</p>

      <QaTodoPanel
        v-if="showQaPanel"
        :run="run"
        :items="qaItems"
        :selected-id="view.selectedObjectId.value"
        :busy="busyAction"
        :on-dispose="disposeItem"
        :on-batch="disposeBatch"
        @select="view.selectObject"
        @locate="locateAnchor"
        @revise="reviseRun"
        @recheck="requalify"
        @termbase="openTermbase"
      />

      <section class="qy-panel qy-run-stages" aria-labelledby="qy-stage-heading">
        <h2 id="qy-stage-heading">阶段事件</h2>
        <StageTimeline
          :events="events"
          :current-stage="run?.stage || ''"
          :quality-state="run?.quality_state || 'draft'"
        />
      </section>

      <TermReviewPanel
        :items="termCandidates"
        :rules="termRules"
        :unresolved="termUnresolved"
        :blocking="termsBlockDelivery(run)"
        :total="termTotal"
        :page="termPage"
        :page-size="40"
        :can-manage-terms="canReviewHighRisk"
        :error="termPanelError"
        :enriching="termEnriching"
        :suggester="termSuggester"
        @decide="decideTerm"
        @batch="batchDecideTerms"
        @page="loadTerms"
        @enrich="enrichTermSuggestions"
        @error="(message) => { termPanelError = message; }"
      />

      <div class="qy-run-detail-grid">
        <section class="qy-panel qy-run-viewer" aria-label="源译对照">
          <DualCanvasViewer
            ref="viewer"
            :run-id="runId"
            :page="view.page.value"
            :zoom="view.zoom.value"
            :sync-scroll="view.sync.value"
            :refresh-key="previewRefreshKey"
            @update:page="view.setPage"
            @update:zoom="view.setZoom"
            @update:sync-scroll="view.setSync"
          />
        </section>
      </div>

      <RunConfirmDrawer
        v-if="drawer && run"
        :mode="drawer.mode"
        :run="run"
        :on-submit="submitDrawer"
        @close="drawer = null"
      />

      <p v-if="!logVisible" class="qy-log-toggle">
        <button type="button" class="qy-link-button" @click="logVisible = true">显示技术日志</button>
      </p>
      <section v-else class="qy-panel qy-log-section">
        <h2>
          <button
            type="button"
            class="qy-secondary-button"
            :aria-expanded="logOpen"
            aria-controls="qy-log-drawer"
            aria-label="技术日志抽屉"
            @click="logOpen = !logOpen"
          >{{ logOpen ? '收起技术日志' : '展开技术日志' }}</button>
          <button type="button" class="qy-link-button" @click="logVisible = false">隐藏</button>
        </h2>
        <pre v-show="logOpen" id="qy-log-drawer" class="qy-log-drawer" tabindex="0" aria-label="技术日志内容">{{ logText }}</pre>
      </section>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
import QaTodoPanel from '../components/QaTodoPanel.vue';
import RunConfirmDrawer from '../components/RunConfirmDrawer.vue';
import DualCanvasViewer from '../components/DualCanvasViewer.vue';
import StageTimeline from '../components/StageTimeline.vue';
import TermReviewPanel from '../components/TermReviewPanel.vue';
import { useRunDetailView } from '../stores/runDetail.js';
import { useAsyncAction } from '../lib/asyncAction.js';
import { confirmDialog } from '../lib/confirm.js';
import { createEventTail } from '../lib/eventTail.js';
import { createPoller } from '../lib/poller.js';
import {
  can,
  isExecuting,
  lifecycleLabel,
  lifecycleOf,
  qualityLabel,
  stageLabel,
  termsBlockDelivery,
} from '../labels.js';
import { useSessionStore } from '../stores/session.js';

const props = defineProps({ runId: { type: String, default: '' } });
const route = useRoute();
const router = useRouter();
const view = useRunDetailView();
const sessionStore = useSessionStore();
const loadError = ref('');
const viewer = ref(null);
const logOpen = ref(false);
const logVisible = ref(false);
const run = ref(null);
const events = ref([]);
const qaItems = ref([]);
const termCandidates = ref([]);
const termRules = ref({});
const termUnresolved = ref(0);
const termTotal = ref(0);
const termPage = ref(1);
const reviewError = ref('');
const termPanelError = ref('');
const termEnriching = ref(false);
const reviewComment = ref('');
const asyncAction = useAsyncAction();
const busyAction = asyncAction.pending;
const drawer = ref(null); // { mode: 'revision' | 'resume', extra? }
const actionNotice = ref('');
const termSuggester = ref(null); // who would receive term snippets if suggestions are requested
const draftError = ref('');
// Parts of the page that failed to load without making the whole page unusable.
const softIssues = ref({});
const softIssueText = computed(() => Object.values(softIssues.value).filter(Boolean).join('；'));
const eventTail = createEventTail((id, params) => api.getRunEvents(id, params));
let autoSelectDone = false;
const canManageTerms = computed(() => sessionStore.hasCapability('can_manage_terms'));
const isRunOwner = computed(() => Boolean(
  run.value?.actor_sub && sessionStore.user?.sub && run.value.actor_sub === sessionStore.user.sub,
));
const canReviewHighRisk = computed(() => canManageTerms.value || isRunOwner.value);
let draftTimer;

function softIssue(key, error, what) {
  softIssues.value = { ...softIssues.value, [key]: error ? `${what}没能加载（${error.network ? '连接中断' : (error.message || '未知错误')}），稍后会再试` : '' };
}

const runId = computed(() => props.runId || route.params.runId);
const sourcePreviewUrl = computed(() => (
  runId.value ? `/api/v1/translation-runs/${encodeURIComponent(runId.value)}/preview/source` : ''
));
const translatedPreviewUrl = computed(() => (
  runId.value ? `/api/v1/translation-runs/${encodeURIComponent(runId.value)}/preview/translated` : ''
));
const logText = computed(() => JSON.stringify({
  status: run.value?.status,
  stage: run.value?.stage,
  quality_state: run.value?.quality_state,
  progress: run.value?.progress,
  events: events.value.slice(-12),
}, null, 2));

const previewRefreshKey = computed(() => [
  run.value?.status, run.value?.stage, run.value?.quality_state,
].join('|'));
const formalGateMessage = computed(() => {
  const gate = run.value?.formal_gate;
  if (!gate || gate.passed) return '';
  const pending = [];
  if (gate.unresolved_term_count && termsBlockDelivery(run.value)) pending.push(`${gate.unresolved_term_count} 条术语`);
  if (gate.qa_blockers) pending.push(`${gate.qa_blockers} 个 QA 阻断项`);
  return pending.length
    ? `正式稿尚未解锁：${pending.join('、')}待处理`
    : '正式稿尚未解锁，请检查当前 QA 与版本状态';
});

const showQaPanel = computed(() => Boolean(run.value) && (
  qaItems.value.length > 0
  || ['qa_action', 'qa_unavailable', 'review', 'changes_requested', 'qa_checking'].includes(lifecycleOf(run.value))
));

const lifecycleBanner = computed(() => {
  const state = lifecycleOf(run.value);
  const pending = run.value?.pending_counts || {};
  if (state === 'qa_unavailable') {
    return {
      title: '质量检查未完成',
      body: '检查服务当时无法运行，这不代表译文有问题，也不能当作检查通过。服务恢复后请点击“重新检查”。',
    };
  }
  if (state === 'qa_action') {
    return {
      title: `还有 ${pending.qa_blockers || 0} 个阻断问题需要处理`,
      body: '处理方式：核对问题处的原文和译文，修正后重新翻译或由有权限的人确认；处理完成后点击“重新检查”。',
    };
  }
  if (state === 'changes_requested') {
    return { title: '已退回修改', body: '本版本已被复核人退回，请根据意见重新翻译或放弃本版本。' };
  }
  return null;
});

const OPEN_TERM_STATUSES = new Set(['pending', 'pending_admin', 'violation']);

function visibleTermItems(items) {
  return (items || []).filter((item) => OPEN_TERM_STATUSES.has(item.status));
}

async function loadTerms(page = termPage.value) {
  const terms = await api.listRunTermCandidates(runId.value, { page, page_size: 40 });
  termCandidates.value = visibleTermItems(terms.items);
  termSuggester.value = terms.suggester || null;
  termRules.value = terms.rules || {};
  termUnresolved.value = terms.unresolved || 0;
  termTotal.value = termCandidates.value.length;
  termPage.value = terms.page || page;
}

async function refresh({ includeTerms = true } = {}) {
  if (!runId.value) return;
  try {
    run.value = await api.getRun(runId.value);
    events.value = await eventTail.pull(runId.value);
    const qa = await api.getQaItems(runId.value);
    qaItems.value = qa.items || [];
    selectFirstBlockerOnce();
    if (includeTerms) {
      try {
        await loadTerms();
        softIssue('terms', null);
      } catch (error) {
        termCandidates.value = [];
        softIssue('terms', error, '术语候选');
      }
    }
    if (run.value?.quality_state === 'review_ready') {
      const draft = await api.getReviewDraft(runId.value);
      reviewComment.value = draft.comment || '';
    }
    loadError.value = '';
  } catch (error) {
    loadError.value = error?.status === 404
      ? '未找到该任务，请返回任务列表确认。'
      : `任务详情加载失败：${error?.message || '未知错误'}`;
  }
  poller.reschedule();
}

// What the person can see change while a task runs; the poll only refetches the rest when this moves.
function runSignature(current) {
  if (!current) return '';
  return [current.status, current.stage, current.quality_state, current.lifecycle, current.generation, current.progress, JSON.stringify(current.pending_counts || {})].join('|');
}

// Detail polls only while the task is executing or being checked, only while the tab is in front, and then
// fetches just the run and any new events; the heavier lists are reloaded when the run itself changed.
const poller = createPoller({
  run: async () => {
    if (!runId.value) return undefined;
    const before = runSignature(run.value);
    try {
      run.value = await api.getRun(runId.value);
      events.value = await eventTail.pull(runId.value);
      loadError.value = '';
    } catch (error) {
      loadError.value = error?.network ? error.message : `任务详情刷新失败：${error?.message || '未知错误'}`;
      throw error;
    }
    const after = runSignature(run.value);
    if (after !== before) await refresh({ includeTerms: false });
    return `${after}#${events.value.length}`;
  },
  shouldPoll: () => isExecuting(run.value),
});

function scheduleDraftSave() {
  window.clearTimeout(draftTimer);
  draftTimer = window.setTimeout(async () => {
    if (!runId.value) return;
    try {
      await api.saveReviewDraft(runId.value, {
        comment: reviewComment.value,
        resolved_qa_ids: qaItems.value.filter((item) => item.resolved).map((item) => item.id),
      });
      draftError.value = '';
    } catch (error) {
      // The text stays in the box; say that it is not saved yet instead of pretending it is.
      draftError.value = error?.network ? '连接中断，审核意见暂未保存；恢复后继续输入会再次保存。' : '审核意见暂未保存，请稍后再试。';
    }
  }, 600);
}

async function approve() {
  try {
    await api.postReviewDecision(runId.value, { decision: 'approve', comment: reviewComment.value || null });
    reviewError.value = '';
    await refresh();
  } catch (error) {
    reviewError.value = error?.message || '正式稿批准失败';
  }
}

// pending -> success/failure feedback for every action, and no double submission.
async function runAction(name, task, { success = '', failure = '操作失败' } = {}) {
  if (asyncAction.pending.value) return false;
  reviewError.value = '';
  actionNotice.value = '';
  const ok = await asyncAction.run(name, task, { success, failure, after: refresh });
  if (ok) actionNotice.value = success;
  else reviewError.value = asyncAction.error.value;
  return ok;
}

function selectFirstBlockerOnce() {
  if (autoSelectDone || view.selectedObjectId.value) return;
  const wanted = route.query.item;
  if (!wanted && route.query.tab !== 'qa') return;
  const first = (wanted && qaItems.value.find((item) => item.id === wanted))
    || qaItems.value.find((item) => item.severity === 'blocker' && !item.resolved)
    || qaItems.value.find((item) => item.severity === 'unavailable' && !item.resolved);
  if (!first) return;
  autoSelectDone = true;
  view.selectObject(first.object_id || `qa:${first.id}`);
}

function requestChanges() {
  return runAction(
    'request_changes',
    () => api.postReviewDecision(runId.value, { decision: 'request_changes', comment: reviewComment.value || null }),
    { success: '已退回修改。', failure: '退回修改失败' },
  );
}

function resumeRun() {
  drawer.value = { mode: 'resume' };
}

function requalify() {
  return runAction('requalify', () => api.requalifyRun(runId.value), {
    success: '已重新检查，结果已更新。',
    failure: '重新检查失败',
  });
}

function retryV2() {
  drawer.value = { mode: 'revision', extra: { pipeline: 'v2' } };
}

// The panel shows failures itself, so these rethrow instead of swallowing them.
async function disposeItem(item, action, reason) {
  await api.postQaDisposition(runId.value, item.id, {
    action,
    reason,
    ...(item.round_id ? { expected_round_id: item.round_id } : {}),
  });
  await refresh({ includeTerms: false });
}

async function disposeBatch(payload) {
  const response = await api.postQaDispositionsBatch(runId.value, payload);
  await refresh({ includeTerms: false });
  return response;
}

// Drives the viewer itself so the page scrolls into view, repeated clicks on the same page still respond,
// and the anchor's side is honoured. Out-of-range and unavailable anchors keep the URL page untouched.
async function locateAnchor(anchor) {
  if (!anchor?.page) return;
  const result = await viewer.value?.focusAnchor?.(anchor);
  if (!result || result.reason === 'pending') view.setPage(anchor.page);
}

// From a term problem straight to the vocabulary workbench, with the term already in the search box.
function openTermbase(search) {
  router.push({ path: '/termbase', query: search ? { q: search } : {} });
}

function reviseRun() {
  drawer.value = { mode: 'revision', extra: {} };
}

// The drawer shows failures itself, so this rethrows instead of swallowing them.
async function submitDrawer(submission) {
  const current = drawer.value;
  if (!current) return;
  if (current.mode === 'resume') {
    await api.resumeRun(runId.value);
    actionNotice.value = '已从断点续跑。';
    drawer.value = null;
    await refresh();
    return;
  }
  const overrides = submission.overrides || {};
  const created = await api.createRevision(runId.value, {
    ...current.extra,
    ...(Object.keys(overrides).length ? { overrides } : {}),
  });
  drawer.value = null;
  if (created?.id) await router.push({ path: `/workbench/${created.id}`, query: { tab: 'qa' } });
}

async function discardRun() {
  const confirmed = await confirmDialog({
    title: '放弃本版本？',
    body: '放弃后将无法继续处理其中的质量问题；审计记录会保留。',
    confirmLabel: '放弃本版本',
    danger: true,
  });
  if (!confirmed) return false;
  return runAction('discard', () => api.cancelRun(runId.value), { success: '已放弃本版本。', failure: '放弃失败' });
}

async function decideTerm(item, payload) {
  try {
    await api.decideRunTermCandidate(runId.value, item.id, payload);
    reviewError.value = '';
    termPanelError.value = '';
    termCandidates.value = termCandidates.value.filter((row) => row.id !== item.id);
    termTotal.value = termCandidates.value.length;
    termUnresolved.value = Math.max(0, termUnresolved.value - 1);
  } catch (error) {
    const message = error?.status === 403
      ? '当前账号不能裁决这条术语。'
      : error?.status === 409
        ? '该术语已被其他审核人更新，请刷新后重试。'
        : (error?.message || '术语裁决失败');
    termPanelError.value = message;
    reviewError.value = message;
  }
}

// Only ever called from the button. When the snippets would leave the network, the person is told
// where they go and has to agree first; opening the page sends nothing anywhere.
async function enrichTermSuggestions() {
  if (termEnriching.value) return;
  const suggester = termSuggester.value;
  if (suggester && suggester.egress_scope !== 'none') {
    const confirmed = await confirmDialog({
      title: '把术语片段发送给外部服务？',
      body: `获取推荐译法会把脱敏后的术语片段发送给 ${suggester.label || '外部模型'}。不需要的话可以取消，手动填写确认译法。`,
      confirmLabel: '发送并获取',
    });
    if (!confirmed) return;
  }
  termEnriching.value = true;
  termPanelError.value = '';
  try {
    const payload = await api.enrichRunTermSuggestions(runId.value);
    termCandidates.value = visibleTermItems(payload.items);
    termSuggester.value = payload.suggester || termSuggester.value;
    termRules.value = payload.rules || {};
    termUnresolved.value = payload.unresolved || 0;
    termTotal.value = payload.total || 0;
    termPage.value = payload.page || termPage.value;
    if ((payload.suggestions_enriched || 0) === 0) {
      termPanelError.value = '没有新的推荐译法；请手动填写确认译法，或联系管理员检查术语模型配置。';
    }
  } catch (error) {
    termPanelError.value = error?.message || '获取推荐译法失败';
  } finally {
    termEnriching.value = false;
  }
}

async function batchDecideTerms(decisions) {
  try {
    await api.batchDecideRunTermCandidates(runId.value, decisions);
    reviewError.value = '';
    await refresh();
  } catch (error) {
    reviewError.value = error?.status === 409
      ? '部分术语已被其他审核人更新，请刷新后重试。'
      : (error?.message || '批量术语裁决失败');
  }
}

watch(runId, async (next, previous) => {
  if (!next || next === previous) return;
  autoSelectDone = false;
  run.value = null;
  qaItems.value = [];
  events.value = [];
  softIssues.value = {};
  draftError.value = '';
  await refresh();
});

onMounted(async () => {
  await sessionStore.load();
  poller.start();
  await refresh();
});
onUnmounted(() => {
  poller.stop();
  window.clearTimeout(draftTimer);
});
</script>

<style scoped>
.qy-run-detail { display: grid; gap: 1rem; min-width: 0; }
.qy-log-toggle { margin: 0; }
.qy-log-section h2 { display: flex; gap: .75rem; align-items: center; }
.qy-run-detail-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
.qy-run-detail-actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
.qy-run-detail-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 1rem; align-items: start; }
.qy-run-viewer, .qy-run-stages, .qy-log-section { padding: .75rem; min-width: 0; }
.qy-run-detail-error { display: flex; gap: 1rem; align-items: center; padding: .75rem; color: #8b1e1e; }
.qy-log-section h2 { margin: 0 0 .5rem; font-size: 1rem; }
.qy-log-drawer { max-height: 240px; overflow: auto; font-size: .8rem; margin: 0; }
.qy-badge { margin-left: .5rem; padding: .1rem .4rem; border: 1px solid currentColor; }
.qy-review-comment { display: grid; gap: .35rem; min-width: min(420px, 100%); }
.qy-review-comment textarea { width: 100%; min-height: 4.5rem; }
@media (max-width: 900px) {
  .qy-run-detail-head { flex-direction: column; }
}
</style>

<template>
  <AppShell>
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
      />

      <section class="qy-panel qy-run-stages" aria-labelledby="qy-stage-heading">
        <h2 id="qy-stage-heading">阶段事件</h2>
        <StageTimeline
          :events="events"
          :current-stage="run?.stage || ''"
          :quality-state="run?.quality_state || 'draft'"
        />
      </section>

      <AffiliationReviewPanel
        :items="affiliationSegments"
        :unconfirmed="affiliationUnconfirmed"
        @decide="decideAffiliation"
        @apply-corrections="applyCorrections"
      />

      <TermReviewPanel
        :items="termCandidates"
        :rules="termRules"
        :unresolved="termUnresolved"
        :total="termTotal"
        :page="termPage"
        :page-size="40"
        :can-manage-terms="canReviewHighRisk"
        :error="termPanelError"
        :enriching="termEnriching"
        @decide="decideTerm"
        @batch="batchDecideTerms"
        @page="loadTerms"
        @enrich="enrichTermSuggestions"
        @error="(message) => { termPanelError = message; }"
      />

      <div class="qy-run-detail-grid">
        <section class="qy-panel qy-run-viewer" aria-label="源译对照">
          <DualCanvasViewer
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
        <section class="qy-panel qy-run-inspector">
          <ObjectInspector
            :items="qaItems"
            :selected-id="view.selectedObjectId.value"
            :show-list="false"
            @select="view.selectObject"
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
import AffiliationReviewPanel from '../components/AffiliationReviewPanel.vue';
import QaTodoPanel from '../components/QaTodoPanel.vue';
import RunConfirmDrawer from '../components/RunConfirmDrawer.vue';
import DualCanvasViewer from '../components/DualCanvasViewer.vue';
import ObjectInspector from '../components/ObjectInspector.vue';
import StageTimeline from '../components/StageTimeline.vue';
import TermReviewPanel from '../components/TermReviewPanel.vue';
import { useRunDetailView } from '../stores/runDetail.js';
import {
  can,
  lifecycleLabel,
  lifecycleOf,
  qualityLabel,
  stageLabel,
} from '../labels.js';
import { useSessionStore } from '../stores/session.js';

const props = defineProps({ runId: { type: String, default: '' } });
const route = useRoute();
const router = useRouter();
const view = useRunDetailView();
const sessionStore = useSessionStore();
const loadError = ref('');
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
const affiliationSegments = ref([]);
const affiliationUnconfirmed = ref(0);
const reviewError = ref('');
const termPanelError = ref('');
const termEnriching = ref(false);
const reviewComment = ref('');
const busyAction = ref('');
const drawer = ref(null); // { mode: 'revision' | 'resume', extra? }
const actionNotice = ref('');
let autoSelectDone = false;
const canManageTerms = computed(() => sessionStore.hasCapability('can_manage_terms'));
const isRunOwner = computed(() => Boolean(
  run.value?.actor_sub && sessionStore.user?.sub && run.value.actor_sub === sessionStore.user.sub,
));
const canReviewHighRisk = computed(() => canManageTerms.value || isRunOwner.value);
let timer;
let draftTimer;

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
  return `尚有 ${gate.unresolved_term_count || 0} 条术语、${gate.unconfirmed_affiliation_count || 0} 条单位译名或 ${gate.qa_blockers || 0} 个 QA 阻断项未处理`;
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
  termRules.value = terms.rules || {};
  termUnresolved.value = terms.unresolved || 0;
  termTotal.value = termCandidates.value.length;
  termPage.value = terms.page || page;
}

async function refresh({ includeTerms = true } = {}) {
  if (!runId.value) return;
  try {
    run.value = await api.getRun(runId.value);
    const ev = await api.getRunEvents(runId.value, { after_sequence: 0 });
    events.value = ev.items || [];
    const qa = await api.getQaItems(runId.value);
    qaItems.value = qa.items || [];
    selectFirstBlockerOnce();
    if (includeTerms) {
      try {
        await loadTerms();
      } catch {
        termCandidates.value = [];
      }
    }
    try {
      const affiliations = await api.listRunAffiliationSegments(runId.value);
      affiliationSegments.value = affiliations.items || [];
      affiliationUnconfirmed.value = affiliations.unconfirmed || 0;
    } catch {
      affiliationSegments.value = [];
      affiliationUnconfirmed.value = 0;
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
}

function scheduleDraftSave() {
  window.clearTimeout(draftTimer);
  draftTimer = window.setTimeout(async () => {
    if (!runId.value) return;
    try {
      await api.saveReviewDraft(runId.value, {
        comment: reviewComment.value,
        resolved_qa_ids: qaItems.value.filter((item) => item.resolved).map((item) => item.id),
      });
    } catch {
      /* ignore transient draft errors */
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
  if (busyAction.value) return false;
  busyAction.value = name;
  reviewError.value = '';
  actionNotice.value = '';
  try {
    await task();
    actionNotice.value = success;
    return true;
  } catch (error) {
    reviewError.value = error?.message || failure;
    return false;
  } finally {
    busyAction.value = '';
    await refresh();
  }
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

function locateAnchor(anchor) {
  if (anchor?.page) view.setPage(anchor.page);
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

function discardRun() {
  if (!window.confirm('放弃本版本后将无法继续处理其中的质量问题（审计记录会保留）。确定放弃吗？')) return false;
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

async function enrichTermSuggestions() {
  termEnriching.value = true;
  termPanelError.value = '';
  try {
    const payload = await api.enrichRunTermSuggestions(runId.value);
    termCandidates.value = visibleTermItems(payload.items);
    termRules.value = payload.rules || {};
    termUnresolved.value = payload.unresolved || 0;
    termTotal.value = payload.total || 0;
    termPage.value = payload.page || termPage.value;
    if ((payload.suggestions_enriched || 0) === 0) {
      termPanelError.value = '没有新的推荐译法；请手动填写确认译法，或检查 DeepSeek 配置。';
    }
  } catch (error) {
    termPanelError.value = error?.message || 'DeepSeek 推断失败';
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

async function decideAffiliation(item, revisedText) {
  try {
    await api.decideRunAffiliationSegment(runId.value, item.id, {
      expected_version: item.version,
      revised_text: revisedText,
    });
    reviewError.value = '';
    await refresh();
  } catch (error) {
    reviewError.value = error?.status === 409
      ? '该单位译名已被其他审核人更新，请刷新后重试。'
      : (error?.message || '单位译名确认失败');
  }
}

async function applyCorrections() {
  try {
    const nextRun = await api.applyRunCorrections(runId.value);
    reviewError.value = '';
    if (nextRun?.id) await router.push(`/workbench/${nextRun.id}`);
  } catch (error) {
    reviewError.value = error?.message || '重新生成失败';
  }
}

watch(runId, async (next, previous) => {
  if (!next || next === previous) return;
  autoSelectDone = false;
  run.value = null;
  qaItems.value = [];
  events.value = [];
  await refresh();
});

onMounted(async () => {
  await sessionStore.load();
  await refresh();
  if (termCandidates.value.some((item) => !item.suggested_target)) {
    await enrichTermSuggestions();
  }
  timer = setInterval(() => refresh({ includeTerms: false }), 3000);
});
onUnmounted(() => {
  clearInterval(timer);
  window.clearTimeout(draftTimer);
});
</script>

<style scoped>
.qy-run-detail { display: grid; gap: 1rem; min-width: 0; }
.qy-log-toggle { margin: 0; }
.qy-log-section h2 { display: flex; gap: .75rem; align-items: center; }
.qy-run-detail-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
.qy-run-detail-actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
.qy-run-detail-grid { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 1rem; align-items: start; }
.qy-run-viewer, .qy-run-inspector, .qy-run-stages, .qy-log-section { padding: .75rem; min-width: 0; }
.qy-run-detail-error { display: flex; gap: 1rem; align-items: center; padding: .75rem; color: #8b1e1e; }
.qy-log-section h2 { margin: 0 0 .5rem; font-size: 1rem; }
.qy-log-drawer { max-height: 240px; overflow: auto; font-size: .8rem; margin: 0; }
.qy-badge { margin-left: .5rem; padding: .1rem .4rem; border: 1px solid currentColor; }
.qy-review-comment { display: grid; gap: .35rem; min-width: min(420px, 100%); }
.qy-review-comment textarea { width: 100%; min-height: 4.5rem; }
@media (max-width: 1023px) {
  .qy-run-detail-grid { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  .qy-run-detail-head { flex-direction: column; }
}
</style>

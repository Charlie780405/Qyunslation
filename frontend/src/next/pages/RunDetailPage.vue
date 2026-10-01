<template>
  <AppShell>
    <div class="qy-run-detail">
      <header class="qy-panel qy-run-detail-head">
        <div>
          <router-link class="qy-link-button" to="/workbench">← 任务列表</router-link>
          <h1>{{ run?.display_name || run?.filename || '任务详情' }}</h1>
          <p>
            状态 {{ run?.status || '…' }} · 阶段 {{ run?.stage || '…' }} ·
            质量 {{ run?.quality_state || 'draft' }}
            <span v-if="run?.quality_state === 'legacy_unverified'" class="qy-badge">旧版未验证</span>
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
            @click="requestChanges"
          >请求修改</button>
          <button
            v-if="run?.quality_state === 'qa_blocked'"
            class="qy-primary-button"
            type="button"
            @click="requalify"
          >重新 QA</button>
          <button
            v-if="run?.status === 'interrupted'"
            class="qy-primary-button"
            type="button"
            @click="resumeRun"
          >从断点续跑</button>
          <button
            v-if="run?.quality_state === 'legacy_unverified'"
            class="qy-secondary-button"
            type="button"
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
          >译文预览</a>
        </div>
      </header>

      <p v-if="loadError" class="qy-panel qy-run-detail-error" role="alert">
        {{ loadError }}
        <button type="button" class="qy-secondary-button" aria-label="重新加载任务详情" @click="refresh">重试</button>
      </p>
      <p v-if="reviewError" class="qy-panel qy-run-detail-error" role="alert">{{ reviewError }}</p>

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
        :can-manage-terms="canManageTerms"
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
            @select="view.selectObject"
          />
        </section>
      </div>

      <section class="qy-panel qy-log-section">
        <h2>
          <button
            type="button"
            class="qy-secondary-button"
            :aria-expanded="logOpen"
            aria-controls="qy-log-drawer"
            aria-label="技术日志抽屉"
            @click="logOpen = !logOpen"
          >{{ logOpen ? '收起技术日志' : '展开技术日志' }}</button>
        </h2>
        <pre v-show="logOpen" id="qy-log-drawer" class="qy-log-drawer" tabindex="0" aria-label="技术日志内容">{{ logText }}</pre>
      </section>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
import AffiliationReviewPanel from '../components/AffiliationReviewPanel.vue';
import DualCanvasViewer from '../components/DualCanvasViewer.vue';
import ObjectInspector from '../components/ObjectInspector.vue';
import StageTimeline from '../components/StageTimeline.vue';
import TermReviewPanel from '../components/TermReviewPanel.vue';
import { useRunDetailView } from '../stores/runDetail.js';
import { useSessionStore } from '../stores/session.js';

const props = defineProps({ runId: { type: String, default: '' } });
const route = useRoute();
const router = useRouter();
const view = useRunDetailView();
const sessionStore = useSessionStore();
const loadError = ref('');
const logOpen = ref(false);
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
const canManageTerms = computed(() => sessionStore.hasCapability('can_manage_terms'));
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

async function loadTerms(page = termPage.value) {
  const terms = await api.listRunTermCandidates(runId.value, { page, page_size: 40 });
  termCandidates.value = terms.items || [];
  termRules.value = terms.rules || {};
  termUnresolved.value = terms.unresolved || 0;
  termTotal.value = terms.total || 0;
  termPage.value = terms.page || page;
}

async function refresh() {
  if (!runId.value) return;
  try {
    run.value = await api.getRun(runId.value);
    const ev = await api.getRunEvents(runId.value, { after_sequence: 0 });
    events.value = ev.items || [];
    const qa = await api.getQaItems(runId.value);
    qaItems.value = qa.items || [];
    try {
      await loadTerms();
    } catch {
      termCandidates.value = [];
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

async function requestChanges() {
  await api.postReviewDecision(runId.value, { decision: 'request_changes', comment: reviewComment.value || null });
  await refresh();
}

async function resumeRun() {
  await api.resumeRun(runId.value);
  await refresh();
}

async function requalify() {
  await api.requalifyRun(runId.value);
  await refresh();
}

async function retryV2() {
  await api.retryRun(runId.value, { pipeline: 'v2' });
  await refresh();
}

async function decideTerm(item, payload) {
  try {
    await api.decideRunTermCandidate(runId.value, item.id, payload);
    reviewError.value = '';
    termPanelError.value = '';
    await refresh();
  } catch (error) {
    const message = error?.status === 409
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
    termCandidates.value = payload.items || [];
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

onMounted(async () => {
  await sessionStore.load();
  await refresh();
  timer = setInterval(refresh, 3000);
});
onUnmounted(() => {
  clearInterval(timer);
  window.clearTimeout(draftTimer);
});
</script>

<style scoped>
.qy-run-detail { display: grid; gap: 1rem; min-width: 0; }
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

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
            @click="approve"
          >批准正式产物</button>
          <button
            v-if="run?.quality_state === 'review_ready'"
            class="qy-secondary-button"
            type="button"
            @click="requestChanges"
          >请求修改</button>
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

      <section class="qy-panel qy-run-stages" aria-labelledby="qy-stage-heading">
        <h2 id="qy-stage-heading">阶段事件</h2>
        <StageTimeline
          :events="events"
          :current-stage="run?.stage || ''"
          :quality-state="run?.quality_state || 'draft'"
        />
      </section>

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
import { useRoute } from 'vue-router';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
import DualCanvasViewer from '../components/DualCanvasViewer.vue';
import ObjectInspector from '../components/ObjectInspector.vue';
import StageTimeline from '../components/StageTimeline.vue';
import { useRunDetailView } from '../stores/runDetail.js';

const props = defineProps({ runId: { type: String, default: '' } });
const route = useRoute();
const view = useRunDetailView();
const loadError = ref('');
const logOpen = ref(false);
const run = ref(null);
const events = ref([]);
const qaItems = ref([]);
const reviewComment = ref('');
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

async function refresh() {
  if (!runId.value) return;
  try {
    run.value = await api.getRun(runId.value);
    const ev = await api.getRunEvents(runId.value, { after_sequence: 0 });
    events.value = ev.items || [];
    const qa = await api.getQaItems(runId.value);
    qaItems.value = qa.items || [];
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
  await api.postReviewDecision(runId.value, { decision: 'approve', comment: reviewComment.value || null });
  await refresh();
}

async function requestChanges() {
  await api.postReviewDecision(runId.value, { decision: 'request_changes', comment: reviewComment.value || null });
  await refresh();
}

async function resumeRun() {
  await api.resumeRun(runId.value);
  await refresh();
}

async function retryV2() {
  await api.retryRun(runId.value, { pipeline: 'v2' });
  await refresh();
}

onMounted(async () => {
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

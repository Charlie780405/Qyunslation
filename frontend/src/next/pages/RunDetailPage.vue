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
          <button
            v-if="run?.quality_state === 'review_ready'"
            class="qy-primary-button"
            type="button"
            @click="approve"
          >批准正式产物</button>
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

      <div class="qy-run-detail-grid">
        <section class="qy-panel">
          <h2>阶段事件</h2>
          <StageTimeline
            :events="events"
            :current-stage="run?.stage || ''"
            :quality-state="run?.quality_state || 'draft'"
          />
        </section>
        <section class="qy-panel">
          <h2>QA 项</h2>
          <ul v-if="qaItems.length" class="qy-qa-list">
            <li v-for="item in qaItems" :key="item.id" :data-severity="item.severity">
              <strong>{{ item.severity }}</strong> {{ item.code }} — {{ item.message }}
            </li>
          </ul>
          <p v-else class="qy-muted">暂无 QA 项</p>
          <h2>技术日志</h2>
          <pre class="qy-log-drawer">{{ logText }}</pre>
        </section>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
import StageTimeline from '../components/StageTimeline.vue';

const props = defineProps({ runId: { type: String, default: '' } });
const route = useRoute();
const router = useRouter();
const run = ref(null);
const events = ref([]);
const qaItems = ref([]);
let timer;

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

async function refresh() {
  if (!runId.value) return;
  run.value = await api.getRun(runId.value);
  const ev = await api.getRunEvents(runId.value, { after_sequence: 0 });
  events.value = ev.items || [];
  const qa = await api.getQaItems(runId.value);
  qaItems.value = qa.items || [];
}

async function approve() {
  await api.postReviewDecision(runId.value, { decision: 'approve' });
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
onUnmounted(() => clearInterval(timer));
</script>

<style scoped>
.qy-run-detail { display: grid; gap: 1rem; }
.qy-run-detail-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
.qy-run-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.qy-qa-list { list-style: none; padding: 0; margin: 0; display: grid; gap: .5rem; }
.qy-qa-list li[data-severity='blocker'] { color: #8b1e1e; }
.qy-log-drawer { max-height: 240px; overflow: auto; font-size: .8rem; }
.qy-badge { margin-left: .5rem; padding: .1rem .4rem; border: 1px solid currentColor; }
@media (max-width: 900px) {
  .qy-run-detail-grid { grid-template-columns: 1fr; }
  .qy-run-detail-head { flex-direction: column; }
}
</style>

<template>
  <AppShell class="qy-run-complete-shell">
    <div class="qy-run-complete" data-run-complete>
      <p><router-link class="qy-link-button" to="/workbench">← 任务列表</router-link></p>
      <p v-if="loadError" class="qy-panel qy-run-detail-error" role="alert">
        {{ loadError }}
        <button type="button" class="qy-secondary-button" @click="load">重试</button>
      </p>
      <p v-else-if="!run" class="qy-panel" role="status">正在加载…</p>

      <template v-else>
        <header class="qy-panel qy-complete-head" :data-state="approved ? 'done' : 'pending'">
          <span class="qy-complete-mark" aria-hidden="true">{{ approved ? '✓' : '!' }}</span>
          <div>
            <h1 data-complete-title>{{ approved ? '正式稿已生成' : '这个版本还没有批准' }}</h1>
            <p class="qy-muted">
              {{ run.display_name || run.filename || '未命名文档' }}
              <template v-if="run.generation"> · 第 {{ run.generation }} 版</template>
              <template v-if="run.source_language && run.target_language"> · {{ run.source_language }} → {{ run.target_language }}</template>
            </p>
          </div>
        </header>

        <section v-if="approved" class="qy-panel qy-complete-files" aria-labelledby="qy-complete-files-heading">
          <h2 id="qy-complete-files-heading">导出</h2>
          <ul v-if="formalArtifacts.length" class="qy-complete-file-list">
            <li v-for="artifact in formalArtifacts" :key="artifact.id" data-complete-file>
              <span class="qy-complete-file-name">
                <strong>{{ artifact.filename }}</strong>
                <small v-if="artifact.size_bytes" class="qy-muted">{{ formatSize(artifact.size_bytes) }}</small>
              </span>
              <a class="qy-primary-button" :href="artifact.download_url" download data-complete-download>下载</a>
            </li>
          </ul>
          <p v-else class="qy-muted" data-complete-no-files>
            没有找到可导出的正式文件。可能还在生成，稍后刷新；仍然没有的话请联系管理员。
            <button type="button" class="qy-secondary-button" @click="load">刷新</button>
          </p>
          <p>
            <a class="qy-link-button" :href="previewUrl" target="_blank" rel="noopener">在线预览译文</a>
          </p>
        </section>

        <section v-else class="qy-panel qy-qa-notice" role="status">
          还没有可导出的正式稿：这个版本需要先通过质量检查并批准。
        </section>

        <section class="qy-panel qy-complete-next" aria-labelledby="qy-complete-next-heading">
          <h2 id="qy-complete-next-heading">还想改一改？</h2>
          <p class="qy-muted">
            回到质量检查页可以查看每一项问题的处理记录；在那里点“生成修订版”会产生新版本，
            新版本检查通过后再批准。<strong>当前这一版的正式稿会保留，仍可下载。</strong>
          </p>
          <div class="qy-complete-actions">
            <router-link class="qy-secondary-button" :to="`/workbench/${runId}`" data-complete-back-to-qa>回到质量检查</router-link>
            <router-link class="qy-link-button" to="/workbench">回到任务列表</router-link>
          </div>
        </section>
      </template>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';

const props = defineProps({ runId: { type: String, required: true } });

const run = ref(null);
const loadError = ref('');

const approved = computed(() => run.value?.quality_state === 'approved' || run.value?.quality_state === 'legacy_unverified');
const formalArtifacts = computed(() => (run.value?.artifacts || []).filter((artifact) => artifact.formal_export || artifact.kind === 'legacy'));
const previewUrl = computed(() => api.previewUrl(props.runId, 'translated'));

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

async function load() {
  loadError.value = '';
  try {
    run.value = await api.getRun(props.runId);
  } catch (error) {
    loadError.value = error?.status === 404 ? '没有找到这个任务。' : (error?.message || '加载失败，请稍后重试。');
  }
}

onMounted(load);
</script>

<style scoped>
.qy-run-complete { display: grid; gap: .9rem; max-width: 56rem; }
.qy-complete-head { display: flex; gap: 1rem; align-items: center; padding: 1rem 1.25rem; }
.qy-complete-head h1 { margin: 0; font-size: 1.4rem; }
.qy-complete-head p { margin: .2rem 0 0; }
.qy-complete-mark { display: grid; place-items: center; flex: none; width: 2.6rem; height: 2.6rem; border-radius: 50%; font-size: 1.4rem; font-weight: 700; color: #fff; background: #2e7d32; }
.qy-complete-head[data-state='pending'] .qy-complete-mark { background: #d97706; }
.qy-complete-files, .qy-complete-next { padding: .9rem 1.25rem; }
.qy-complete-files h2, .qy-complete-next h2 { margin: 0 0 .6rem; font-size: 1.05rem; }
.qy-complete-file-list { list-style: none; padding: 0; margin: 0 0 .5rem; display: grid; gap: .5rem; }
.qy-complete-file-list li { display: flex; gap: 1rem; align-items: center; justify-content: space-between; padding: .55rem .75rem; border: 1px solid var(--qy-border, #d6dce3); border-radius: 6px; background: #fff; }
.qy-complete-file-name { display: grid; gap: .1rem; min-width: 0; overflow-wrap: anywhere; }
.qy-complete-file-list .qy-primary-button { flex: none; width: auto; text-decoration: none; }
.qy-complete-actions { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; }
.qy-complete-actions .qy-secondary-button { width: auto; text-decoration: none; }
@media (max-width: 640px) { .qy-complete-file-list li { flex-direction: column; align-items: stretch; } }
</style>

<template>
  <AppShell>
    <section class="qy-page-head">
      <div>
        <span class="qy-eyebrow">TRANSLATION WORKSPACE</span>
        <h1>翻译工作台</h1>
        <p>从文件预检开始，逐步完成翻译、质量检查和受控交付。</p>
      </div>
      <div class="qy-page-head-actions">
        <button class="qy-secondary-button" type="button" @click="showAdvanced = !showAdvanced">
          <AdjustmentsHorizontalIcon aria-hidden="true" /> {{ showAdvanced ? '收起参数' : '本次任务参数' }}
        </button>
      </div>
    </section>

    <div class="qy-workbench-grid">
      <section class="qy-workbench-main">
        <div class="qy-panel qy-upload-panel">
          <div class="qy-panel-heading">
            <div><span class="qy-step-index">01</span><div><h2>上传文档</h2><p>先做结构预检，再决定是否开始翻译。</p></div></div>
            <span class="qy-panel-status">尚未开始</span>
          </div>
          <div class="qy-language-fields" aria-label="翻译语言">
            <label class="qy-field"><span>源语言</span><select v-model="workbenchState.sourceLanguage"><option v-for="language in languages" :key="language" :value="language">{{ language }}</option></select></label>
            <label class="qy-field"><span>目标语言</span><select v-model="workbenchState.targetLanguage"><option v-for="language in languages" :key="language" :value="language">{{ language }}</option></select></label>
          </div>
          <div v-if="languageError" class="qy-callout qy-callout-warning" role="alert"><InformationCircleIcon aria-hidden="true" /><span>{{ languageError }}</span></div>
          <label class="qy-dropzone" :class="{ 'is-selected': selectedFile }" for="workbench-file">
            <input id="workbench-file" ref="fileInput" type="file" class="qy-visually-hidden" accept=".pdf,.docx,.pptx,.txt,.md" @change="selectFile" />
            <DocumentArrowUpIcon aria-hidden="true" />
            <strong>{{ selectedFile ? selectedFile.name : '拖放文件到这里，或点击选择' }}</strong>
            <span>{{ selectedFile ? formatSize(selectedFile.size) : '支持 PDF、DOCX、PPTX、TXT、Markdown' }}</span>
          </label>
          <div v-if="uploadMessage" class="qy-callout" :class="uploadError ? 'qy-callout-warning' : 'qy-callout-info'" role="status">
            <InformationCircleIcon aria-hidden="true" /><span>{{ uploadMessage }}</span>
          </div>
          <div v-if="activeRun" class="qy-live-progress" role="status" aria-live="polite">
            <div class="qy-live-progress-heading">
              <div class="qy-live-progress-title"><span class="qy-live-indicator" aria-hidden="true"></span><strong>翻译实时进度</strong></div>
              <span>{{ statusLabel(activeRun.status) }}</span>
            </div>
            <div class="qy-live-progress-meta"><strong>{{ activeRun.progress_message || stageMessage(activeRun) }}</strong><span>{{ progressText(activeRun) }}</span></div>
            <div
              class="qy-task-progress qy-live-progress-bar"
              :class="{ 'is-indeterminate': activeRun.progress === null || activeRun.progress === undefined }"
              role="progressbar"
              :aria-valuemin="0"
              :aria-valuemax="100"
              :aria-valuenow="activeRun.progress === null || activeRun.progress === undefined ? undefined : activeRun.progress"
              :aria-valuetext="progressText(activeRun)"
            ><span :style="activeRun.progress === null || activeRun.progress === undefined ? {} : { width: `${Math.max(0, Math.min(100, activeRun.progress))}%` }"></span></div>
            <StageTimeline
              :events="activeEvents"
              :current-stage="activeRun.stage || ''"
              :quality-state="activeRun.quality_state || 'draft'"
            />
          </div>
          <div v-if="preflight" class="qy-preflight-card" aria-live="polite">
            <div><strong>{{ preflight.filename }}</strong><span>{{ preflight.format?.toUpperCase() }} · {{ formatSize(preflight.size_bytes) }} · SHA-256 已记录</span></div>
            <span class="qy-status-badge" :class="preflight.state === 'ready' ? 'is-ready' : 'is-pending'">{{ preflight.state === 'ready' ? '预检通过' : '需要处理' }}</span>
            <button class="qy-primary-button" type="button" :disabled="startingRun || preflight.state !== 'ready' || activeRun?.preflight_id === preflight.id" @click="startTranslation">
              <ArrowPathIcon v-if="startingRun" class="qy-spin" aria-hidden="true" />
              <PlayIcon v-else aria-hidden="true" />
              {{ startingRun ? '正在创建任务…' : activeRun?.preflight_id === preflight.id ? '翻译进行中' : '确认并开始翻译' }}
            </button>
          </div>
          <div class="qy-panel-actions">
            <button class="qy-primary-button" type="button" :disabled="!selectedFile || uploading" @click="startPreflight">
              <ArrowPathIcon v-if="uploading" class="qy-spin" aria-hidden="true" />
              <MagnifyingGlassIcon v-else aria-hidden="true" />
              {{ uploading ? (uploadProgress < 100 ? `上传中 ${uploadProgress}%` : '正在检查文件…') : '开始预检' }}
            </button>
            <span class="qy-inline-hint">不会自动开始翻译</span>
          </div>
        </div>

        <div class="qy-panel qy-task-panel">
          <div class="qy-panel-heading">
            <div><span class="qy-step-index qy-step-muted">02</span><div><h2>最近任务</h2><p>离开页面后，任务仍会在服务端继续运行。</p></div></div>
            <div class="qy-task-toolbar">
              <label class="qy-check-field"><input v-model="showArchived" type="checkbox" /><span>显示已归档</span></label>
              <button class="qy-link-button" type="button" @click="refreshRuns">刷新</button>
            </div>
          </div>
          <div v-if="runs.length" class="qy-task-list">
            <article v-for="run in runs" :key="run.id" class="qy-task-row" @click="openRun(run)">
              <div class="qy-task-file-icon"><DocumentTextIcon aria-hidden="true" /></div>
              <div class="qy-task-details">
                <strong>{{ run.display_name || run.filename || run.file_name || '未命名文档' }}</strong>
                <span>{{ run.source_language || 'English' }} → {{ run.target_language || '简体中文' }} · {{ statusLabel(run.status) }} · {{ stageLabel(run.stage) }}<template v-if="run.progress !== null && run.progress !== undefined"> · {{ run.progress }}%</template><template v-if="run.quality_state === 'legacy_unverified'"> · 旧版未验证</template></span>
                <div v-if="isActive(run)" class="qy-task-live-line"><span class="qy-live-indicator" aria-hidden="true"></span><span>{{ run.progress_message || stageMessage(run) }}</span><span>{{ progressText(run) }}</span></div>
                <div v-if="isActive(run)" class="qy-task-progress" :class="{ 'is-indeterminate': run.progress === null || run.progress === undefined }" role="progressbar" :aria-valuemin="0" :aria-valuemax="100" :aria-valuenow="run.progress === null || run.progress === undefined ? undefined : run.progress" :aria-valuetext="progressText(run)"><span :style="run.progress === null || run.progress === undefined ? {} : { width: `${Math.max(0, Math.min(100, run.progress))}%` }"></span></div>
                <div v-if="run.artifacts?.length" class="qy-task-artifacts">
                  <a v-for="artifact in run.artifacts" :key="artifact.id" :href="artifact.download_url" download @click.stop>{{ artifact.filename }}</a>
                </div>
              </div>
              <div class="qy-task-actions" @click.stop>
                <button v-if="isActive(run)" class="qy-link-button" type="button" @click="cancelRun(run)">取消</button>
                <button v-else-if="canResume(run)" class="qy-link-button" type="button" @click="resumeRunAction(run)">续跑</button>
                <button v-else-if="canRetryV2(run)" class="qy-link-button" type="button" @click="retryRun(run, { pipeline: 'v2' })">新版重试</button>
                <button v-else-if="canRetry(run)" class="qy-link-button" type="button" @click="retryRun(run)">重试</button>
                <button v-if="run.archived" class="qy-link-button" type="button" @click="restoreRun(run)">恢复</button>
                <button v-else-if="isTerminal(run)" class="qy-link-button" type="button" @click="archiveRun(run)">归档</button>
                <button v-if="isTerminal(run)" class="qy-link-button qy-danger-link" type="button" @click="deleteRun(run)">删除</button>
                <button class="qy-link-button" type="button" @click="renameRun(run)">重命名</button>
                <ChevronRightIcon aria-hidden="true" />
              </div>
            </article>
          </div>
          <div v-else class="qy-empty-state">
            <ClockIcon aria-hidden="true" />
            <strong>还没有翻译任务</strong>
            <span>上传一份文档后，预检结果会显示在这里。</span>
          </div>
        </div>
      </section>

      <aside class="qy-workbench-side">
        <div class="qy-panel qy-side-card">
          <span class="qy-eyebrow">TASK FLOW</span>
          <h2>真实阶段事件</h2>
          <p class="qy-muted">进度只反映服务端事件，不伪造已完成。</p>
          <StageTimeline
            :events="activeEvents"
            :current-stage="activeRun?.stage || ''"
            :quality-state="activeRun?.quality_state || 'draft'"
          />
        </div>
        <div v-if="showAdvanced" class="qy-panel qy-settings-card">
          <div class="qy-panel-heading"><div><h2>本次任务参数</h2><p>开始翻译后将固定为任务快照。</p></div><LockClosedIcon aria-hidden="true" /></div>
          <label class="qy-field"><span>文档类型</span><select v-model="workbenchState.profile"><option>临床研究文档</option><option>监管申报材料</option><option>通用医药文档</option></select></label>
          <label class="qy-field"><span>资料等级</span><select v-model="workbenchState.classification"><option value="internal">内部</option><option value="confidential">机密</option><option value="public">公开</option></select></label>
          <label class="qy-check-field"><input v-model="workbenchState.bilingual" type="checkbox" /><span>生成源译对照稿</span></label>
        </div>
      </aside>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
import { useSessionStore } from '../stores/session.js';
import {
  restoredPreflight,
  restoreWorkbenchSession,
  scheduleWorkbenchPreferenceSave,
  uploadStorageKey,
  workbenchState,
} from '../stores/workbench.js';
import StageTimeline from '../components/StageTimeline.vue';
import {
  AdjustmentsHorizontalIcon,
  ArrowPathIcon,
  ChevronRightIcon,
  ClockIcon,
  DocumentArrowUpIcon,
  DocumentTextIcon,
  InformationCircleIcon,
  LockClosedIcon,
  MagnifyingGlassIcon,
  PlayIcon,
} from '@heroicons/vue/24/outline';

const router = useRouter();
const sessionStore = useSessionStore();
const selectedFile = ref(null);
const fileInput = ref(null);
const uploadMessage = ref('');
const uploadError = ref(false);
const uploading = ref(false);
const uploadProgress = ref(0);
const showAdvanced = ref(false);
const runs = ref([]);
const activeEvents = ref([]);
const preflight = ref(null);
const startingRun = ref(false);
const showArchived = ref(false);
let pollTimer;
let pollRequest = 0;

const activeStatuses = new Set(['queued', 'scanning', 'translating', 'rendering']);
const terminalStatuses = new Set(['review_ready', 'succeeded', 'failed', 'cancelled', 'blocked', 'degraded']);
const languages = ['English', '简体中文'];
const activeRun = computed(() => runs.value.find(isActive) || null);
const languageError = computed(() => workbenchState.sourceLanguage === workbenchState.targetLanguage ? '源语言和目标语言不能相同。' : '');

// HTTP field values are restricted to ISO-8859-1 by the browser Headers API.
// Encode each segment so localized settings remain safe and deterministic as
// an Idempotency-Key while still distinguishing every task configuration.
function buildIdempotencyKey() {
  return [
    'preflight',
    preflight.value?.id,
    workbenchState.sourceLanguage,
    workbenchState.targetLanguage,
    workbenchState.profile,
    workbenchState.bilingual ? '1' : '0',
  ].map((value) => encodeURIComponent(String(value ?? ''))).join(':');
}

function statusLabel(status) {
  return ({ queued: '排队中', scanning: '结构分析', translating: '翻译中', rendering: '渲染中', review_ready: '待复核', succeeded: '已完成', failed: '失败', cancelled: '已取消', blocked: '已阻断', degraded: '降级完成', interrupted: '已中断' })[status] || '待处理';
}

function stageLabel(stage) {
  return ({ validation: '预检', structure: '结构', text: '正文', table_figure: '表格与图注', layout: '版式', rendering: '版式', qa: 'QA', review: '复核', export: '导出' })[stage] || '处理中';
}

function isActive(run) {
  return activeStatuses.has(run.status);
}

function isTerminal(run) {
  return terminalStatuses.has(run.status);
}

function canRetry(run) {
  return ['failed', 'cancelled', 'blocked', 'degraded'].includes(run.status);
}

function canResume(run) {
  return run.status === 'interrupted';
}

function canRetryV2(run) {
  return run.quality_state === 'legacy_unverified' || canRetry(run);
}

function openRun(run) {
  if (!run?.id) return;
  router.push(`/workbench/${run.id}`);
}

function stageMessage(run) {
  return ({ validation: '正在准备任务', structure: '正在分析文档结构', text: '正在翻译正文', table_figure: '正在处理表格与图注', layout: '正在渲染版式', rendering: '正在渲染版式', qa: '正在执行 QA 检查', review: '等待人工复核', export: '正在导出结果' })[run?.stage] || '正在处理任务';
}

function progressText(run) {
  return run?.progress === null || run?.progress === undefined ? '处理中，进度计算中' : `${run.progress}%`;
}

function selectFile(event) {
  selectedFile.value = event.target.files?.[0] || null;
  preflight.value = null;
  uploadProgress.value = 0;
  uploadMessage.value = selectedFile.value ? '文件已选择，点击“开始预检”查看结构和风险。' : '';
  uploadError.value = false;
}

function formatSize(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

async function startPreflight() {
  if (!selectedFile.value) return;
  if (languageError.value) {
    uploadError.value = true;
    uploadMessage.value = languageError.value;
    return;
  }
  uploading.value = true;
  uploadProgress.value = 0;
  uploadError.value = false;
  uploadMessage.value = '';
  try {
    const storageKey = uploadStorageKey(sessionStore.user?.tenant_slug, sessionStore.user?.sub);
    preflight.value = await api.uploadPreflightResumable(
      selectedFile.value,
      {
        source_language: workbenchState.sourceLanguage,
        target_language: workbenchState.targetLanguage,
        profile: workbenchState.profile,
      },
      (progress) => { uploadProgress.value = progress; },
      storageKey,
    );
    uploadMessage.value = preflight.value.state === 'ready'
      ? (preflight.value.reused ? '已复用相同文件的预检结果，请确认参数后开始翻译。' : '预检已完成。请确认参数后再开始翻译。')
      : '预检发现风险，请先处理阻断项。';
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.status === 404 ? '预检服务正在接入，当前仅完成工作台界面预览。' : error.message;
  } finally {
    uploading.value = false;
    uploadProgress.value = 100;
  }
}

async function startTranslation() {
  if (!preflight.value || preflight.value.state !== 'ready' || activeRun.value?.preflight_id === preflight.value.id) return;
  startingRun.value = true;
  uploadError.value = false;
  try {
    const key = buildIdempotencyKey();
    await api.createTranslationRun({
      preflight_id: preflight.value.id,
      source_language: workbenchState.sourceLanguage,
      target_language: workbenchState.targetLanguage,
      profile: workbenchState.profile,
      bilingual: workbenchState.bilingual,
      document_classification: workbenchState.classification,
    }, key);
    uploadMessage.value = '翻译任务已创建，服务端会继续处理。';
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    if (error.status === 404 && String(error.message || '').toLowerCase().includes('preflight not found')) {
      preflight.value = null;
      uploadMessage.value = '预检记录已失效，请重新点击“开始预检”后再翻译。';
    } else {
      uploadMessage.value = error.message || '翻译任务创建失败';
    }
  } finally {
    startingRun.value = false;
  }
}

async function refreshActiveEvents(run) {
  if (!run?.id) {
    activeEvents.value = [];
    return;
  }
  try {
    const response = await api.getRunEvents(run.id, { after_sequence: 0 });
    activeEvents.value = response.items || [];
  } catch {
    activeEvents.value = [];
  }
}

async function refreshRuns() {
  const requestId = ++pollRequest;
  try {
    const response = await api.listRuns({ include_archived: showArchived.value ? 'true' : 'false' });
    if (requestId !== pollRequest) return;
    runs.value = Array.isArray(response) ? response : response.items || [];
    const focus = runs.value.find(isActive) || runs.value[0];
    await refreshActiveEvents(focus);
  } catch {
    if (requestId === pollRequest && !runs.value.length) runs.value = [];
  } finally {
    if (requestId !== pollRequest) return;
    window.clearTimeout(pollTimer);
    const active = runs.value.some(isActive);
    pollTimer = window.setTimeout(refreshRuns, active ? 2000 : 10000);
  }
}

async function cancelRun(run) {
  try {
    await api.cancelRun(run.id);
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '取消任务失败';
  }
}

async function resumeRunAction(run) {
  try {
    await api.resumeRun(run.id);
    uploadMessage.value = '任务已从断点续跑。';
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '续跑失败';
  }
}

async function retryRun(run, payload = {}) {
  try {
    await api.retryRun(run.id, payload);
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '重试任务失败';
  }
}

async function archiveRun(run) {
  try {
    await api.patchRun(run.id, { archived: true });
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '归档任务失败';
  }
}

async function restoreRun(run) {
  try {
    await api.restoreRun(run.id);
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '恢复任务失败';
  }
}

async function renameRun(run) {
  const nextName = window.prompt('输入任务名称', run.display_name || run.filename || '');
  if (nextName === null || nextName.trim() === (run.display_name || '')) return;
  try {
    await api.patchRun(run.id, { display_name: nextName.trim() });
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '重命名任务失败';
  }
}

async function deleteRun(run) {
  if (!window.confirm(`确定删除任务“${run.display_name || run.filename || '未命名文档'}”吗？此操作不可恢复。`)) return;
  try {
    await api.deleteRun(run.id);
    const deletedSelectedPreflight = preflight.value?.id === run.preflight_id;
    if (deletedSelectedPreflight) {
      preflight.value = null;
      uploadError.value = false;
      uploadMessage.value = '任务已删除，原预检记录也已清理。请重新开始预检。';
    }
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '删除任务失败';
  }
}

onMounted(async () => {
  await sessionStore.load();
  await restoreWorkbenchSession(sessionStore.user);
  if (preflight.value === null && restoredPreflight.value?.state === 'ready') {
    preflight.value = restoredPreflight.value;
    uploadMessage.value = '已恢复上次预检结果，可直接开始翻译。';
  }
  await refreshRuns();
});
watch(showArchived, refreshRuns);
watch(workbenchState, () => scheduleWorkbenchPreferenceSave(), { deep: true });
onUnmounted(() => window.clearTimeout(pollTimer));
</script>

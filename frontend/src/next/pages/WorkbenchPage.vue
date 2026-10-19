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

    <section v-if="todoSummary" class="qy-panel qy-todo-bar" data-todo-bar role="status" aria-live="polite">
      <span class="qy-todo-text">
        <strong v-if="todoSummary.action">{{ todoSummary.action }} 个任务需要处理质量问题</strong>
        <template v-if="todoSummary.action && todoSummary.review"> · </template>
        <span v-if="todoSummary.review">{{ todoSummary.review }} 个待人工复核</span>
      </span>
      <button class="qy-secondary-button" type="button" @click="openRun(todoSummary.first, entryTab(todoSummary.first))">
        {{ todoSummary.action ? '去处理' : '去复核' }}
      </button>
    </section>

    <div class="qy-workbench-grid">
      <section class="qy-workbench-main">
        <div class="qy-panel qy-upload-panel">
          <div class="qy-panel-heading">
            <div><span class="qy-step-index">01</span><div><h2>上传文档</h2><p>先做结构预检，再决定是否开始翻译。</p></div></div>
            <span class="qy-panel-status">{{ uploadStatusLabel }}</span>
          </div>
          <div class="qy-language-fields" aria-label="翻译语言">
            <label class="qy-field"><span>源语言</span><select v-model="workbenchState.sourceLanguage"><option v-for="language in languages" :key="language" :value="language">{{ language }}</option></select></label>
            <label class="qy-field"><span>目标语言</span><select v-model="workbenchState.targetLanguage"><option v-for="language in languages" :key="language" :value="language">{{ language }}</option></select></label>
          </div>
          <div class="qy-ad-mode" aria-label="专业领域模式">
            <label class="qy-field"><span>专业领域</span><select v-model="workbenchState.domainProfile"><option value="general">通用医药翻译</option><option v-if="adEnabled" value="ad">AD 特应性皮炎</option></select></label>
            <span class="qy-inline-hint"><span v-if="workbenchState.domainProfile === 'ad'" class="qy-status-badge is-pending" role="status">AD 内部测试版</span>AD 模式仅支持中英互译，并在任务中启用专业提示词、术语和双向 QA。</span>
          </div>
          <div v-if="languageError" class="qy-callout qy-callout-warning" role="alert"><InformationCircleIcon aria-hidden="true" /><span>{{ languageError }}</span></div>
          <label
            class="qy-dropzone"
            :class="{ 'is-selected': selectedFile, 'is-dragging': dragging }"
            for="workbench-file"
            @dragenter.prevent="onDragOver"
            @dragover.prevent="onDragOver"
            @dragleave="onDragLeave"
            @drop.prevent="onDrop"
          >
            <input id="workbench-file" ref="fileInput" type="file" class="qy-visually-hidden" :accept="ACCEPT_ATTRIBUTE" @change="selectFile" />
            <DocumentArrowUpIcon aria-hidden="true" />
            <strong>{{ selectedFile ? selectedFile.name : '拖放文件到这里，或点击选择' }}</strong>
            <span>{{ selectedFile ? formatSize(selectedFile.size) : '支持 PDF、DOCX、PPTX、TXT、Markdown、PNG、JPG' }}</span>
          </label>
          <div v-if="uploadMessage" class="qy-callout" :class="uploadError ? 'qy-callout-warning' : 'qy-callout-info'" role="status">
            <InformationCircleIcon aria-hidden="true" /><span>{{ uploadMessage }}</span>
          </div>
          <div v-if="activeRun" class="qy-live-progress" role="status" aria-live="polite">
            <div class="qy-live-progress-heading">
              <div class="qy-live-progress-title"><span class="qy-live-indicator" aria-hidden="true"></span><strong>翻译实时进度</strong></div>
              <span>{{ lifecycleLabel(activeRun) }}</span>
            </div>
            <div class="qy-live-progress-meta">
              <strong>{{ liveSummary(activeRun) }}</strong>
              <span>{{ progressText(activeRun) }}</span>
            </div>
            <div
              class="qy-task-progress qy-live-progress-bar"
              :class="{ 'is-indeterminate': activeRun.progress === null || activeRun.progress === undefined }"
              role="progressbar"
              :aria-valuemin="0"
              :aria-valuemax="100"
              :aria-valuenow="activeRun.progress === null || activeRun.progress === undefined ? undefined : activeRun.progress"
              :aria-valuetext="progressText(activeRun)"
            ><span :style="activeRun.progress === null || activeRun.progress === undefined ? {} : { width: `${Math.max(0, Math.min(100, activeRun.progress))}%` }"></span></div>
          </div>
          <div v-if="preflight" class="qy-preflight-card" aria-live="polite">
            <div><strong>{{ preflight.filename }}</strong><span>{{ preflight.format?.toUpperCase() }} · {{ formatSize(preflight.size_bytes) }} · SHA-256 已记录</span></div>
            <span class="qy-status-badge" :class="preflight.state === 'ready' ? 'is-ready' : 'is-pending'">{{ preflight.state === 'ready' ? '预检通过' : '需要处理' }}</span>
            <button class="qy-primary-button" type="button" :disabled="startingRun || preflight.state !== 'ready' || Boolean(runForPreflight)" @click="startTranslation">
              <ArrowPathIcon v-if="startingRun" class="qy-spin" aria-hidden="true" />
              <PlayIcon v-else aria-hidden="true" />
              {{ startingRun ? '正在创建任务…' : runForPreflight ? '该文件已创建任务' : '确认并开始翻译' }}
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
                <span>{{ run.source_language || 'English' }} → {{ run.target_language || '简体中文' }} · <strong class="qy-lifecycle" :data-lifecycle="lifecycleOf(run)">{{ lifecycleLabel(run) }}</strong><template v-if="isActive(run)"> · {{ stageLabel(run.stage) }}</template><template v-if="isActive(run) && run.progress !== null && run.progress !== undefined"> · {{ run.progress }}%</template><template v-if="run.quality_state === 'legacy_unverified'"> · 旧版未验证</template></span>
                <div v-if="isActive(run)" class="qy-task-live-line"><span class="qy-live-indicator" aria-hidden="true"></span><span>{{ liveSummary(run) }}</span><span>{{ progressText(run) }}</span></div>
                <div v-if="isActive(run)" class="qy-task-progress" :class="{ 'is-indeterminate': run.progress === null || run.progress === undefined }" role="progressbar" :aria-valuemin="0" :aria-valuemax="100" :aria-valuenow="run.progress === null || run.progress === undefined ? undefined : run.progress" :aria-valuetext="progressText(run)"><span :style="run.progress === null || run.progress === undefined ? {} : { width: `${Math.max(0, Math.min(100, run.progress))}%` }"></span></div>
                <div v-if="run.artifacts?.length" class="qy-task-artifacts">
                  <a v-for="artifact in run.artifacts" :key="artifact.id" :href="artifact.download_url" download @click.stop>{{ artifact.filename }}</a>
                </div>
              </div>
              <div class="qy-task-actions" @click.stop>
                <button v-if="can(run, 'cancel')" class="qy-link-button" type="button" @click="cancelRun(run)">取消</button>
                <button v-if="entryLabel(run)" class="qy-link-button qy-task-entry" type="button" @click="openRun(run, entryTab(run))">{{ entryLabel(run) }}</button>
                <button v-if="can(run, 'resume') && lifecycleOf(run) === 'interrupted'" class="qy-link-button" type="button" @click="resumeRunAction(run)">续跑</button>
                <button v-else-if="canRetryV2(run)" class="qy-link-button" type="button" @click="retryRun(run, { pipeline: 'v2' })">新版重试</button>
                <button v-else-if="can(run, 'retry') && ['failed', 'cancelled'].includes(lifecycleOf(run))" class="qy-link-button" type="button" @click="retryRun(run)">重试</button>
                <button v-if="can(run, 'restore')" class="qy-link-button" type="button" @click="restoreRun(run)">恢复</button>
                <button v-else-if="can(run, 'archive')" class="qy-link-button" type="button" @click="archiveRun(run)">归档</button>
                <button v-if="can(run, 'delete')" class="qy-link-button qy-danger-link" type="button" @click="deleteRun(run)">删除</button>
                <button v-if="can(run, 'rename')" class="qy-link-button" type="button" @click="renameRun(run)">重命名</button>
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
          <p v-if="focusRun" class="qy-muted qy-timeline-owner">当前任务：{{ focusRun.display_name || focusRun.filename || '未命名文档' }}（{{ lifecycleLabel(focusRun) }}）</p>
          <StageTimeline
            :events="activeEvents"
            :current-stage="focusRun?.stage || ''"
            :quality-state="focusRun?.quality_state || 'draft'"
          />
        </div>
        <div v-if="showAdvanced" class="qy-panel qy-settings-card">
          <div class="qy-panel-heading"><div><h2>本次任务参数</h2><p>开始翻译后将固定为任务快照。</p></div><LockClosedIcon aria-hidden="true" /></div>
          <label class="qy-field"><span>文档类型</span><select v-model="workbenchState.profile"><option v-for="option in documentProfileOptions" :key="option">{{ option }}</option></select></label>
          <p v-if="workbenchState.domainProfile === 'ad'" class="qy-muted">AD 模式只支持医学研究文献与临床研究文档。</p>
          <label class="qy-field"><span>资料等级</span><select v-model="workbenchState.classification" @change="refreshModelProfiles"><option value="internal">内部</option><option value="confidential">机密</option><option value="public">公开</option></select></label>
          <label class="qy-field"><span>翻译模型</span><select v-model="workbenchState.modelProfileId"><option v-for="profile in translatorProfiles" :key="profile.profile_id" :value="profile.profile_id" :disabled="!profile.configured">{{ profile.label }}{{ profile.experimental ? '（试验）' : '' }}</option></select></label>
          <p v-if="selectedModelProfile" class="qy-muted">外发范围：{{ egressLabel(selectedModelProfile) }}</p>
          <label class="qy-check-field"><input v-model="workbenchState.bilingual" data-field="bilingual" type="checkbox" :disabled="!bilingualSupported" /><span>生成源译对照稿</span></label>
          <p v-if="!bilingualSupported" class="qy-muted">仅 PDF 支持源译对照；当前格式只输出译文。</p>
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
  can,
  isExecuting,
  lifecycleLabel,
  lifecycleOf,
  stageLabel,
  todoCount,
} from '../labels.js';
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

// Keep in step with PREFLIGHT_ALLOWED_EXTENSIONS in qyunslation/api/v1.py.
const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.txt', '.md', '.png', '.jpg', '.jpeg'];
const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.join(',');
const dragging = ref(false);
const languages = ['English', '简体中文'];
const activeRun = computed(() => runs.value.find(isActive) || null);
// The side timeline always describes one explicit task: the running one, else the newest.
const focusRun = computed(() => activeRun.value || runs.value[0] || null);
const runForPreflight = computed(() => (
  preflight.value ? runs.value.find((item) => item.preflight_id === preflight.value.id) || null : null
));
// What needs a person right now, across every task in the list.
const todoSummary = computed(() => {
  const needsAction = runs.value.filter((item) => ['qa_action', 'qa_unavailable'].includes(lifecycleOf(item)));
  const needsReview = runs.value.filter((item) => lifecycleOf(item) === 'review');
  if (!needsAction.length && !needsReview.length) return null;
  return {
    action: needsAction.length,
    review: needsReview.length,
    first: needsAction[0] || needsReview[0],
  };
});
const uploadStatusLabel = computed(() => {
  if (uploading.value) return '上传预检中';
  if (preflight.value) return preflight.value.state === 'ready' ? '预检通过，待确认参数' : '预检发现问题';
  if (selectedFile.value) return '待预检';
  return '等待选择文件';
});
const adEnabled = computed(() => Boolean(sessionStore.user?.capabilities?.ad_enabled));
// Mirrors SUPPORTED_AD_DOCUMENTS on the server; AD rejects any other profile with 422.
const AD_DOCUMENT_PROFILES = ['医学研究文献', '临床研究文档'];
const GENERAL_DOCUMENT_PROFILES = ['临床研究文档', '监管申报材料', '通用医药文档'];
const documentProfileOptions = computed(() =>
  workbenchState.domainProfile === 'ad' ? AD_DOCUMENT_PROFILES : GENERAL_DOCUMENT_PROFILES,
);
const languageError = computed(() => workbenchState.sourceLanguage === workbenchState.targetLanguage ? '源语言和目标语言不能相同。' : '');
// Only the PDF executor can emit a source/translation pair (see bilingual_effective on the server).
const currentFormat = computed(() => {
  if (preflight.value?.format) return String(preflight.value.format).toLowerCase();
  const name = selectedFile.value?.name || '';
  return name.includes('.') ? name.split('.').pop().toLowerCase() : '';
});
const bilingualSupported = computed(() => !currentFormat.value || currentFormat.value === 'pdf');
const modelProfiles = ref([]);
const translatorProfiles = computed(() => modelProfiles.value.filter((item) => !item.role || item.role === 'translator'));
const selectedModelProfile = computed(
  () => modelProfiles.value.find((item) => item.profile_id === workbenchState.modelProfileId) || null,
);

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
    workbenchState.domainProfile,
    workbenchState.classification,
    workbenchState.modelProfileId,
    workbenchState.bilingual && bilingualSupported.value ? '1' : '0',
  ].map((value) => encodeURIComponent(String(value ?? ''))).join(':');
}

function liveSummary(run) {
  if (!run) return '';
  if (lifecycleOf(run) === 'qa_checking') return '翻译完成，正在做质量检查';
  if (run.status === 'translating' && run.progress_message) return run.progress_message;
  return stageMessage(run);
}

function egressLabel(profile) {
  if (!profile) return '仅内网';
  if (profile.role === 'term_suggester') return '脱敏术语片段';
  if (profile.provider === 'deepseek') return '公开资料全文外发';
  return '无外发';
}

async function refreshModelProfiles() {
  try {
    const payload = await api.listModelProfiles(workbenchState.classification);
    modelProfiles.value = payload.items || payload.profiles || [];
    const current = modelProfiles.value.find((item) => item.profile_id === workbenchState.modelProfileId);
    if (!current || !current.configured) {
      const fallback = modelProfiles.value.find((item) => item.configured && item.role === 'translator');
      if (fallback) workbenchState.modelProfileId = fallback.profile_id;
    }
  } catch {
    modelProfiles.value = [];
  }
}

function isActive(run) {
  return isExecuting(run);
}

function canRetryV2(run) {
  return run.quality_state === 'legacy_unverified' && can(run, 'retry');
}

// One click from a task row to what the person has to do next.
function entryLabel(run) {
  const lifecycle = lifecycleOf(run);
  if (lifecycle === 'qa_action') return `处理质量问题（${todoCount(run)}）`;
  if (lifecycle === 'qa_unavailable') return '查看并重新检查';
  if (lifecycle === 'review') return run.formal_gate && run.formal_gate.passed === false ? '处理待办项' : '去复核';
  if (lifecycle === 'changes_requested') return '查看退回意见';
  return '';
}

function entryTab(run) {
  return ['qa_action', 'qa_unavailable'].includes(lifecycleOf(run)) ? 'qa' : 'review';
}

function openRun(run, tab = '') {
  if (!run?.id) return;
  router.push(tab ? { path: `/workbench/${run.id}`, query: { tab } } : `/workbench/${run.id}`);
}

function stageMessage(run) {
  return ({ validation: '正在准备任务', structure: '正在分析文档结构', text: '正在翻译正文', table_figure: '正在处理表格与图注', layout: '正在渲染版式', rendering: '正在渲染版式', qa: '正在执行 QA 检查', review: '等待人工复核', export: '正在导出结果' })[run?.stage] || '正在处理任务';
}

function progressText(run) {
  return run?.progress === null || run?.progress === undefined ? '处理中，进度计算中' : `${run.progress}%`;
}

function applyFile(file, notice = '') {
  selectedFile.value = file;
  preflight.value = null;
  uploadProgress.value = 0;
  uploadMessage.value = file ? `${notice}文件已选择，点击“开始预检”查看结构和风险。` : '';
  uploadError.value = false;
}

function selectFile(event) {
  applyFile(event.target.files?.[0] || null);
}

function hasFiles(event) {
  return Array.from(event.dataTransfer?.types || []).includes('Files');
}

function onDragOver(event) {
  if (hasFiles(event)) dragging.value = true;
}

function onDragLeave(event) {
  // Moving between the zone's children fires dragleave on the zone; only clear
  // the highlight when the pointer really left it.
  if (event.currentTarget?.contains?.(event.relatedTarget)) return;
  dragging.value = false;
}

function onDrop(event) {
  dragging.value = false;
  const files = Array.from(event.dataTransfer?.files || []);
  if (!files.length) return;
  const file = files[0];
  const extension = file.name.includes('.') ? `.${file.name.split('.').pop().toLowerCase()}` : '';
  if (!ACCEPTED_EXTENSIONS.includes(extension)) {
    uploadError.value = true;
    uploadMessage.value = `不支持的文件格式“${extension || file.name}”。请使用 PDF、DOCX、PPTX、TXT、Markdown、PNG 或 JPG。`;
    return;
  }
  applyFile(file, files.length > 1 ? '一次只能处理一个文件，已使用第一个。' : '');
}

// A file dropped outside the zone must not navigate the tab away to the file.
function ignoreStrayFileDrop(event) {
  if (hasFiles(event)) event.preventDefault();
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
      domain_profile: workbenchState.domainProfile,
      bilingual: workbenchState.bilingual && bilingualSupported.value,
      document_classification: workbenchState.classification,
      model_profile_id: workbenchState.modelProfileId,
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
  window.addEventListener('dragover', ignoreStrayFileDrop);
  window.addEventListener('drop', ignoreStrayFileDrop);
  await sessionStore.load();
  await restoreWorkbenchSession(sessionStore.user);
  await refreshModelProfiles();
  if (preflight.value === null && restoredPreflight.value?.state === 'ready') {
    preflight.value = restoredPreflight.value;
    uploadMessage.value = '已恢复上次预检结果，可直接开始翻译。';
  }
  await refreshRuns();
});
watch(adEnabled, (enabled) => {
  if (!enabled && workbenchState.domainProfile === 'ad') {
    workbenchState.domainProfile = 'general';
  }
});
watch(
  () => workbenchState.domainProfile,
  (domain) => {
    if (domain === 'ad' && !AD_DOCUMENT_PROFILES.includes(workbenchState.profile)) {
      workbenchState.profile = '临床研究文档';
    } else if (domain !== 'ad' && !GENERAL_DOCUMENT_PROFILES.includes(workbenchState.profile)) {
      workbenchState.profile = '临床研究文档';
    }
  },
);
watch(showArchived, refreshRuns);
watch(() => workbenchState.classification, refreshModelProfiles);
watch(workbenchState, () => scheduleWorkbenchPreferenceSave(), { deep: true });
onUnmounted(() => {
  window.clearTimeout(pollTimer);
  window.removeEventListener('dragover', ignoreStrayFileDrop);
  window.removeEventListener('drop', ignoreStrayFileDrop);
});
</script>

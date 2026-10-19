<template>
  <AppShell>
    <section class="qy-page-head">
      <div>
        <span class="qy-eyebrow">TRANSLATION WORKSPACE</span>
        <h1>翻译工作台</h1>
        <p>从文件预检开始，逐步完成翻译、质量检查和受控交付。</p>
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
          <label
            class="qy-dropzone"
            :class="{ 'is-selected': selectedFile, 'is-dragging': dragging }"
            for="workbench-file"
            @dragenter.prevent="onDragOver"
            @dragover.prevent="onDragOver"
            @dragleave="onDragLeave"
            @drop.prevent="onDrop"
          >
            <input id="workbench-file" ref="fileInput" type="file" class="qy-visually-hidden" :accept="acceptAttribute" @change="selectFile" />
            <DocumentArrowUpIcon aria-hidden="true" />
            <strong>{{ selectedFile ? selectedFile.name : '拖放文件到这里，或点击选择' }}</strong>
            <span>{{ selectedFile ? formatSize(selectedFile.size) : `支持 ${formatList.join('、')}${maxBytes ? `，单个文件不超过 ${formatSize(maxBytes)}` : ''}` }}</span>
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
            <button class="qy-primary-button" type="button" :disabled="preflight.state !== 'ready' || Boolean(runForPreflight)" @click="openConfirm">
              <PlayIcon aria-hidden="true" />
              {{ runForPreflight ? '该文件已创建任务' : '确认参数并开始翻译' }}
            </button>
            <button v-if="runForPreflight && preflight.state === 'ready'" class="qy-secondary-button" type="button" @click="copyAndConfirm">用新参数再翻译一次</button>
          </div>
          <PreflightIssues :preflight="preflight" />
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
              <span v-if="list.loaded.value" class="qy-muted" data-run-total>共 {{ list.total.value }} 个任务</span>
              <button class="qy-link-button" type="button" @click="refreshRuns">刷新</button>
            </div>
          </div>
          <RunListToolbar :model-value="list.filters" :facets="list.facets.value" @update:model-value="changeFilters" />
          <div v-if="list.status.value === 'error' && runs.length" class="qy-inline-alert" role="alert" data-run-stale>
            <span>刷新失败，下面是上次加载的内容：{{ list.error.value }}</span>
            <button class="qy-link-button" type="button" @click="refreshRuns">重试</button>
          </div>
          <div v-if="!list.loaded.value && list.status.value === 'loading'" class="qy-empty-state" role="status" data-run-loading>
            <ArrowPathIcon class="qy-spin" aria-hidden="true" />
            <strong>正在加载任务…</strong>
          </div>
          <div v-else-if="!runs.length && list.status.value === 'error'" class="qy-empty-state" role="alert" data-run-error>
            <strong>任务列表加载失败</strong>
            <span>{{ list.error.value }}</span>
            <button class="qy-secondary-button" type="button" @click="refreshRuns">重试</button>
          </div>
          <div v-else-if="runs.length" class="qy-task-list" :aria-busy="list.status.value === 'loading'">
            <div class="qy-select-head" data-select-head>
              <label class="qy-check-field">
                <input type="checkbox" data-select-page :checked="list.pageSelected.value" @change="togglePage" />
                <span>全选本页</span>
              </label>
              <span v-if="list.allMatching.value" class="qy-muted" data-select-banner>
                已选择全部 {{ list.allMatching.value.count }} 条筛选结果
              </span>
              <span v-else-if="list.pageSelected.value && list.total.value > runs.length" class="qy-muted" data-select-banner>
                已选择本页 {{ runs.length }} 项 ·
                <button class="qy-link-button" type="button" data-select-all :disabled="list.selectionBusy.value" @click="selectEverything">选择全部 {{ list.total.value }} 条筛选结果</button>
              </span>
              <span v-if="list.selectionNotice.value" class="qy-muted" role="status" data-select-notice>{{ list.selectionNotice.value }}</span>
            </div>
            <article v-for="run in runs" :key="run.id" class="qy-task-row" :class="{ 'is-selected': list.isSelected(run.id), 'is-trashed': isTrash }" :data-run-id="run.id" tabindex="-1" @click="onRowClick(run)">
              <label class="qy-row-check" @click.stop>
                <input type="checkbox" data-row-select :checked="list.isSelected(run.id)" :aria-label="`选择 ${rowName(run)}`" @change="list.toggle(run.id)" />
              </label>
              <div class="qy-task-file-icon"><DocumentTextIcon aria-hidden="true" /></div>
              <div class="qy-task-details">
                <div v-if="renaming?.id === run.id" class="qy-rename" @click.stop>
                  <input
                    ref="renameInput"
                    v-model="renaming.value"
                    class="qy-input"
                    data-rename-input
                    maxlength="120"
                    aria-label="任务名称"
                    :disabled="renaming.saving"
                    @keydown.enter.prevent="commitRename"
                    @keydown.esc.prevent="cancelRename"
                  />
                  <button class="qy-link-button" type="button" data-rename-save :disabled="renaming.saving" @click="commitRename()">保存</button>
                  <button v-if="run.display_name" class="qy-link-button" type="button" data-rename-reset :disabled="renaming.saving" @click="commitRename(true)">恢复为原文件名</button>
                  <button class="qy-link-button" type="button" data-rename-cancel :disabled="renaming.saving" @click="cancelRename">取消</button>
                  <span v-if="renaming.error" class="qy-field-error" role="alert" data-rename-error>{{ renaming.error }}</span>
                </div>
                <strong v-else>{{ run.display_name || run.filename || run.file_name || '未命名文档' }}<span v-if="run.version_count > 1 || run.generation > 1" class="qy-version-tag" data-run-version> v{{ run.generation || 1 }}<template v-if="run.version_count > 1">/共 {{ run.version_count }} 版</template></span></strong>
                <span>{{ run.source_language || 'English' }} → {{ run.target_language || '简体中文' }} · <strong class="qy-lifecycle" :data-lifecycle="lifecycleOf(run)">{{ lifecycleLabel(run) }}</strong><template v-if="isActive(run)"> · {{ stageLabel(run.stage) }}</template><template v-if="isActive(run) && run.progress !== null && run.progress !== undefined"> · {{ run.progress }}%</template><template v-if="run.quality_state === 'legacy_unverified'"> · 旧版未验证</template></span>
                <div v-if="isActive(run)" class="qy-task-live-line"><span class="qy-live-indicator" aria-hidden="true"></span><span>{{ liveSummary(run) }}</span><span>{{ progressText(run) }}</span></div>
                <div v-if="isActive(run)" class="qy-task-progress" :class="{ 'is-indeterminate': run.progress === null || run.progress === undefined }" role="progressbar" :aria-valuemin="0" :aria-valuemax="100" :aria-valuenow="run.progress === null || run.progress === undefined ? undefined : run.progress" :aria-valuetext="progressText(run)"><span :style="run.progress === null || run.progress === undefined ? {} : { width: `${Math.max(0, Math.min(100, run.progress))}%` }"></span></div>
                <span v-if="isTrash" class="qy-trash-note" data-trash-note>
                  <template v-if="run.purge_status === 'pending'">正在永久清除…</template>
                  <template v-else-if="run.purge_status === 'failed'">永久清除失败，管理员可以重试</template>
                  <template v-else>已在回收站 · 还剩 {{ run.trash_days_left ?? '—' }} 天后永久清除</template>
                </span>
                <div v-if="run.artifacts?.length && !isTrash" class="qy-task-artifacts">
                  <a v-for="artifact in run.artifacts" :key="artifact.id" :href="artifact.download_url" download @click.stop>{{ artifact.filename }}</a>
                </div>
              </div>
              <div class="qy-task-actions" @click.stop>
                <template v-if="isTrash">
                  <button v-if="can(run, 'restore_from_trash')" class="qy-link-button" type="button" data-trash-restore @click="restoreFromTrash(run)">恢复</button>
                  <button v-if="can(run, 'purge')" class="qy-link-button qy-danger-link" type="button" data-trash-purge @click="askPurge(run)">永久清除</button>
                </template>
                <template v-else>
                  <button v-if="can(run, 'cancel')" class="qy-link-button" type="button" @click="cancelRun(run)">取消</button>
                  <button v-if="entryLabel(run)" class="qy-link-button qy-task-entry" type="button" @click="openRun(run, entryTab(run))">{{ entryLabel(run) }}</button>
                  <button v-if="can(run, 'resume') && lifecycleOf(run) === 'interrupted'" class="qy-link-button" type="button" @click="openResume(run)">续跑</button>
                  <button v-else-if="canRetryV2(run)" class="qy-link-button" type="button" @click="openRevision(run, { pipeline: 'v2' })">新版重试</button>
                  <button v-else-if="can(run, 'retry') && ['failed', 'cancelled'].includes(lifecycleOf(run))" class="qy-link-button" type="button" @click="openRevision(run)">重试</button>
                  <button class="qy-link-button" type="button" @click="copyConfig(run)">复制配置</button>
                  <button v-if="can(run, 'restore')" class="qy-link-button" type="button" @click="restoreRun(run)">恢复</button>
                  <button v-else-if="can(run, 'archive')" class="qy-link-button" type="button" @click="archiveRun(run)">归档</button>
                  <button v-if="can(run, 'delete')" class="qy-link-button qy-danger-link" type="button" @click="deleteRun(run)">删除</button>
                  <button v-if="can(run, 'rename')" class="qy-link-button" type="button" @click="renameRun(run)">重命名</button>
                </template>
                <ChevronRightIcon v-if="!isTrash" aria-hidden="true" />
              </div>
            </article>
          </div>
          <div v-else-if="isTrash" class="qy-empty-state" data-trash-empty>
            <ClockIcon aria-hidden="true" />
            <strong>回收站里没有任务</strong>
            <span>删除的任务会在这里保留 30 天，期间可以恢复。</span>
          </div>
          <div v-else-if="list.filtered.value" class="qy-empty-state" data-run-nomatch>
            <MagnifyingGlassIcon aria-hidden="true" />
            <strong>没有符合条件的任务</strong>
            <span>换个关键词或放宽筛选试试。</span>
            <button class="qy-secondary-button" type="button" @click="resetFilters">清除筛选</button>
          </div>
          <div v-else class="qy-empty-state" data-run-empty>
            <ClockIcon aria-hidden="true" />
            <strong>还没有翻译任务</strong>
            <span>上传一份文档后，预检结果会显示在这里。</span>
          </div>
          <p v-if="batchError" class="qy-field-error" role="alert" data-batch-error>{{ batchError }}</p>
          <div v-if="list.nextCursor.value" class="qy-load-more" data-run-more>
            <button class="qy-secondary-button" type="button" :disabled="list.loadingMore.value" @click="list.loadMore()">
              {{ list.loadingMore.value ? '加载中…' : `加载更多（已显示 ${runs.length} / 共 ${list.total.value}）` }}
            </button>
          </div>
        </div>
      </section>

      <aside class="qy-workbench-side">
        <div class="qy-panel qy-side-card">
          <span class="qy-eyebrow">TASK FLOW</span>
          <h2>真实阶段事件</h2>
          <p class="qy-muted">进度只反映服务端事件，不伪造已完成。</p>
          <p v-if="focusRun" class="qy-muted qy-timeline-owner">当前任务：{{ focusRun.display_name || focusRun.filename || '未命名文档' }}（{{ lifecycleLabel(focusRun) }}）</p>
          <p v-if="eventsError" class="qy-muted qy-events-error" role="status" data-events-error>阶段事件暂时没能更新（{{ eventsError }}），稍后会自动重试。</p>
          <StageTimeline
            :events="activeEvents"
            :current-stage="focusRun?.stage || ''"
            :quality-state="focusRun?.quality_state || 'draft'"
          />
        </div>
      </aside>
    </div>

    <BatchActionBar
      ref="batchBar"
      :count="list.selectionCount.value"
      :rows="list.selectedRows.value"
      :all-matching="Boolean(list.allMatching.value)"
      :excluded-count="list.allMatching.value ? list.allMatching.value.excluded.size : 0"
      :in-trash="isTrash"
      :busy="batchBusy"
      :result="batchResult"
      @run="runBatch"
      @clear="list.clearSelection()"
      @retry-failed="retryFailed"
      @dismiss-result="batchResult = null"
    />

    <RunConfirmDrawer
      v-if="drawer"
      :mode="drawer.mode"
      :preflight="drawer.mode === 'new' ? preflight : null"
      :run="drawer.run || null"
      :initial="drawerInitial"
      :initial-source="drawerInitialSource"
      :defaults="defaultsSnapshot"
      :last="lastConfig"
      :ad-enabled="adEnabled"
      :on-submit="submitDrawer"
      @close="drawer = null"
      @copy-preflight="copyPreflightForDrawer"
    />
  </AppShell>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
import { useSessionStore } from '../stores/session.js';
import { filtersFromQuery, filtersToQuery, listView, runList } from '../stores/runs.js';
import {
  restoredPreflight,
  restoreWorkbenchSession,
  saveWorkbenchDefaults,
  uploadStorageKey,
  workbenchState,
} from '../stores/workbench.js';
import RunConfirmDrawer from '../components/RunConfirmDrawer.vue';
import RunListToolbar from '../components/RunListToolbar.vue';
import BatchActionBar from '../components/BatchActionBar.vue';
import StageTimeline from '../components/StageTimeline.vue';
import PreflightIssues from '../components/PreflightIssues.vue';
import { confirmDialog } from '../lib/confirm.js';
import { createEventTail } from '../lib/eventTail.js';
import { sha256Hex } from '../lib/fileHash.js';
import { createPoller } from '../lib/poller.js';
import {
  can,
  isExecuting,
  lifecycleLabel,
  lifecycleOf,
  stageLabel,
  todoCount,
} from '../labels.js';
import {
  ArrowPathIcon,
  ChevronRightIcon,
  ClockIcon,
  DocumentArrowUpIcon,
  DocumentTextIcon,
  InformationCircleIcon,
  MagnifyingGlassIcon,
  PlayIcon,
} from '@heroicons/vue/24/outline';

const router = useRouter();
const route = useRoute();
const list = runList;
const sessionStore = useSessionStore();
const selectedFile = ref(null);
const fileInput = ref(null);
const uploadMessage = ref('');
const uploadError = ref(false);
const uploading = ref(false);
const uploadProgress = ref(0);
const runs = list.items;
const batchBar = ref(null);
const batchBusy = ref(false);
const batchResult = ref(null);
const batchError = ref('');
const renaming = ref(null); // { id, value, original, version, saving, error }
const renameInput = ref(null);
const preflight = ref(null);
const startingRun = ref(false);
const drawer = ref(null); // { mode: 'new' | 'revision' | 'resume', run?, extra? }
const defaultsSnapshot = ref({});
const copiedFrom = ref(null); // { label, config } carried into the next confirmation
let pollRequest = 0;
const activeEvents = ref([]);
const eventsError = ref('');
const eventTail = createEventTail((id, params) => api.getRunEvents(id, params));

// The server publishes the formats and size limit (/settings/schema); until it answers, or if it cannot,
// the list below (the same one the server ships today) keeps the upload box working.
const FALLBACK_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.txt', '.md', '.png', '.jpg', '.jpeg'];
const FORMAT_NAMES = { '.pdf': 'PDF', '.docx': 'DOCX', '.pptx': 'PPTX', '.txt': 'TXT', '.md': 'Markdown', '.png': 'PNG', '.jpg': 'JPG', '.jpeg': 'JPG' };
const acceptedExtensions = ref([...FALLBACK_EXTENSIONS]);
const maxBytes = ref(0);
const acceptAttribute = computed(() => acceptedExtensions.value.join(','));
const formatList = computed(() => [...new Set(acceptedExtensions.value.map((ext) => FORMAT_NAMES[ext] || ext.replace('.', '').toUpperCase()))]);
const dragging = ref(false);
const activeRun = computed(() => runs.value.find(isActive) || null);
// The side timeline always describes one explicit task: the running one, else the newest.
const focusRun = computed(() => activeRun.value || runs.value[0] || null);
const runForPreflight = computed(() => (
  preflight.value ? runs.value.find((item) => item.preflight_id === preflight.value.id) || null : null
));
// What needs a person right now, across every task in the list.
const isTrash = computed(() => list.filters.archived === 'trash');
const todoSummary = computed(() => {
  if (isTrash.value) return null;
  const needsAction = runs.value.filter((item) => ['qa_action', 'qa_unavailable'].includes(lifecycleOf(item)));
  const needsReview = runs.value.filter((item) => lifecycleOf(item) === 'review');
  // The list may be filtered or paged, so unfiltered counts come from the server's facets.
  const counts = list.filtered.value ? {} : list.facets.value.lifecycle || {};
  const actionTotal = ((counts.qa_action || 0) + (counts.qa_unavailable || 0)) || needsAction.length;
  const reviewTotal = counts.review || needsReview.length;
  const first = needsAction[0] || needsReview[0];
  if (!first) return null;
  return { action: actionTotal, review: reviewTotal, first };
});
const uploadStatusLabel = computed(() => {
  if (uploading.value) return '上传预检中';
  if (preflight.value) return preflight.value.state === 'ready' ? '预检通过，待确认参数' : '预检发现问题';
  if (selectedFile.value) return '待预检';
  return '等待选择文件';
});
const adEnabled = computed(() => Boolean(sessionStore.user?.capabilities?.ad_enabled));
function liveSummary(run) {
  if (!run) return '';
  if (lifecycleOf(run) === 'qa_checking') return '翻译完成，正在做质量检查';
  if (run.status === 'translating' && run.progress_message) return run.progress_message;
  return stageMessage(run);
}

// ---- the confirmation drawer: settings live there and only there --------------------------------
function configFromRun(run) {
  const settings = run.settings || {};
  return {
    sourceLanguage: settings.source_language || run.source_language || 'English',
    targetLanguage: settings.target_language || run.target_language || '简体中文',
    profile: settings.profile || run.profile || '临床研究文档',
    domainProfile: settings.domain_profile || 'general',
    classification: run.document_classification || settings.document_classification || 'internal',
    modelProfileId: run.model_profile_id || settings.model_profile_id || '',
    bilingual: settings.bilingual ?? true,
  };
}

const drawerInitial = computed(() => {
  const base = copiedFrom.value ? copiedFrom.value.config : { ...workbenchState };
  return {
    displayName: '',
    sourceLanguage: base.sourceLanguage,
    targetLanguage: base.targetLanguage,
    profile: base.profile,
    domainProfile: adEnabled.value ? base.domainProfile : 'general',
    classification: base.classification,
    modelProfileId: base.modelProfileId,
    bilingual: base.bilingual,
  };
});
const drawerInitialSource = computed(() => (copiedFrom.value ? copiedFrom.value.label : '上次使用'));
const lastConfig = computed(() => {
  const latest = runs.value[0];
  return latest ? { label: '上次任务', ...configFromRun(latest) } : null;
});

function openConfirm() {
  if (!preflight.value || preflight.value.state !== 'ready' || runForPreflight.value) return;
  drawer.value = { mode: 'new' };
}

async function swapInPreflightCopy() {
  const copy = await api.copyPreflight(preflight.value.id);
  preflight.value = copy;
}

async function copyAndConfirm() {
  try {
    await swapInPreflightCopy();
    drawer.value = { mode: 'new' };
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '复制预检失败';
  }
}

async function copyPreflightForDrawer() {
  try {
    await swapInPreflightCopy();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '复制预检失败';
  }
}

function openRevision(run, extra = {}) {
  drawer.value = { mode: 'revision', run, extra };
}

function openResume(run) {
  drawer.value = { mode: 'resume', run };
}

function copyConfig(run) {
  const name = run.display_name || run.filename || '未命名文档';
  copiedFrom.value = { label: `复制自「${name}」`, config: configFromRun(run) };
  uploadError.value = false;
  uploadMessage.value = `已载入「${name}」的配置。选择文件并预检后，会在确认抽屉里使用这份配置。`;
  document.getElementById('workbench-file')?.focus?.();
}

// The drawer shows failures itself, so submissions rethrow instead of swallowing them.
async function submitDrawer(submission) {
  const current = drawer.value;
  if (!current) return;
  if (current.mode === 'new') {
    await api.createTranslationRun(submission.payload, submission.key);
    uploadError.value = false;
    uploadMessage.value = '翻译任务已创建，服务端会继续处理。';
    copiedFrom.value = null;
    drawer.value = null;
    if (submission.saveAsDefault) {
      const form = submission.form;
      try {
        await saveWorkbenchDefaults({
          sourceLanguage: form.sourceLanguage,
          targetLanguage: form.targetLanguage,
          profile: form.profile,
          domainProfile: form.domainProfile,
          bilingual: form.bilingual,
          classification: form.classification,
          modelProfileId: form.modelProfileId,
        });
        defaultsSnapshot.value = { ...workbenchState };
      } catch (error) {
        uploadError.value = true;
        uploadMessage.value = `任务已创建，但默认参数保存失败：${error.message || '未知错误'}`;
      }
    }
  } else if (current.mode === 'revision') {
    const overrides = submission.overrides || {};
    await api.createRevision(current.run.id, {
      ...current.extra,
      ...(Object.keys(overrides).length ? { overrides } : {}),
    });
    uploadError.value = false;
    uploadMessage.value = '已生成新版本，原版本保持冻结。';
    drawer.value = null;
  } else {
    await api.resumeRun(current.run.id);
    uploadError.value = false;
    uploadMessage.value = '任务已从断点续跑。';
    drawer.value = null;
  }
  await refreshRuns();
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

function rowName(run) {
  return run.display_name || run.filename || run.file_name || '未命名文档';
}

function onRowClick(run) {
  if (!isTrash.value) openRun(run); // a task in the bin cannot be opened, only restored
}

function togglePage(event) {
  if (event.target.checked) list.selectPage();
  else list.clearSelection();
}

async function selectEverything() {
  batchError.value = '';
  try {
    await list.selectAllMatching();
  } catch (error) {
    batchError.value = error.message || '无法选择全部筛选结果';
  }
}

// One path for a batch and for "retry the failed ones": run, show the answer, refresh, drop the selection.
async function applyBatch(action, options) {
  batchBusy.value = true;
  batchError.value = '';
  try {
    batchResult.value = await list.runBatch(action, options);
    list.clearSelection();
    await refreshRuns();
  } catch (error) {
    if (error.status === 410) list.clearSelection('这次选择已过期，请重新选择。');
    batchError.value = error.message || '批量操作失败';
  } finally {
    batchBusy.value = false;
  }
}

function runBatch(action) {
  batchResult.value = null;
  return applyBatch(action);
}

function retryFailed() {
  const result = batchResult.value;
  if (!result) return Promise.resolve();
  const ids = result.items.filter((item) => item.outcome === 'failed').map((item) => item.id);
  return applyBatch(result.action, { onlyIds: ids });
}

async function restoreFromTrash(run) {
  try {
    await api.restoreRunFromTrash(run.id);
    uploadError.value = false;
    uploadMessage.value = `已恢复“${rowName(run)}”。`;
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '恢复失败';
  }
}

async function askPurge(run) {
  list.selectOnly(run.id);
  await nextTick();
  batchBar.value?.ask('purge');
}

function openRun(run, tab = '') {
  if (!run?.id) return;
  listView.scrollY = window.scrollY;
  listView.openedId = run.id;
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

function extensionOf(name) {
  return name.includes('.') ? `.${name.split('.').pop().toLowerCase()}` : '';
}

// One check for a picked and a dropped file, with the reason on screen when it is turned away.
function acceptFile(file, notice = '') {
  const extension = extensionOf(file.name);
  if (!acceptedExtensions.value.includes(extension)) {
    uploadError.value = true;
    uploadMessage.value = `不支持的文件格式“${extension || file.name}”。请使用 ${formatList.value.join('、')}。`;
    return false;
  }
  if (maxBytes.value && file.size > maxBytes.value) {
    uploadError.value = true;
    uploadMessage.value = `文件太大（${formatSize(file.size)}），单个文件不能超过 ${formatSize(maxBytes.value)}。`;
    return false;
  }
  applyFile(file, notice);
  return true;
}

function selectFile(event) {
  const file = event.target.files?.[0] || null;
  if (!file) {
    applyFile(null);
    return;
  }
  if (!acceptFile(file)) event.target.value = '';
}

async function loadUploadLimits() {
  try {
    const upload = (await api.getSettingsSchema())?.upload;
    if (Array.isArray(upload?.allowed_extensions) && upload.allowed_extensions.length) {
      acceptedExtensions.value = upload.allowed_extensions.map((ext) => String(ext).toLowerCase());
    }
    if (upload?.max_bytes) maxBytes.value = Number(upload.max_bytes);
  } catch {
    // Not fatal and not worth a message: the built-in format list stays and the server checks again on upload.
  }
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
  acceptFile(files[0], files.length > 1 ? '一次只能处理一个文件，已使用第一个。' : '');
}

// A file dropped outside the zone must not navigate the tab away to the file.
function ignoreStrayFileDrop(event) {
  if (hasFiles(event)) event.preventDefault();
}

function formatWhen(iso) {
  const date = iso ? new Date(iso) : null;
  if (!date || Number.isNaN(date.getTime())) return '之前';
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getMonth() + 1}月${date.getDate()}日 ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatSize(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

async function startPreflight() {
  if (!selectedFile.value) return;
  uploading.value = true;
  uploadProgress.value = 0;
  uploadError.value = false;
  uploadMessage.value = '';
  try {
    const storageKey = uploadStorageKey(sessionStore.user?.tenant_slug, sessionStore.user?.sub);
    // Hash first (skipped for very large files): the server can then answer with the pre-check it already has.
    const expectedSha256 = await sha256Hex(selectedFile.value);
    preflight.value = await api.uploadPreflightResumable(
      selectedFile.value,
      {
        source_language: workbenchState.sourceLanguage,
        target_language: workbenchState.targetLanguage,
        profile: workbenchState.profile,
      },
      (progress) => { uploadProgress.value = progress; },
      storageKey,
      { expectedSha256 },
    );
    uploadMessage.value = preflight.value.state === 'ready'
      ? (preflight.value.reused
        ? `已复用 ${formatWhen(preflight.value.created_at)} 做过的预检，文件无需重新上传。请确认参数后开始翻译。`
        : '预检已完成。请确认参数后再开始翻译。')
      : '预检发现问题，请先看下面的说明；阻断项处理之前不能开始翻译。';
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.status === 404 ? '预检服务正在接入，当前仅完成工作台界面预览。' : error.message;
  } finally {
    uploading.value = false;
    uploadProgress.value = 100;
  }
}

// Events only grow, so after the first read just the new ones are fetched. A failed read keeps what is on
// screen and says so next to the timeline; the next poll tries again.
async function refreshActiveEvents(run) {
  if (!run?.id) {
    eventTail.reset();
    activeEvents.value = [];
    eventsError.value = '';
    return;
  }
  try {
    activeEvents.value = await eventTail.pull(run.id);
    eventsError.value = '';
  } catch (error) {
    eventsError.value = error.network ? '连接中断' : (error.message || '加载失败');
  }
}

// What the person can see about the list; the poller backs off while this stops changing.
function listSignature() {
  return `${list.total.value}#${runs.value.map((item) => `${item.id}:${lifecycleOf(item)}:${item.stage || ''}:${item.progress ?? ''}`).join('|')}`;
}

// The list is polled only while a task is executing (or being checked) and the tab is in front;
// 2s -> 5s -> 10s while nothing changes. Every other path refreshes on demand.
const poller = createPoller({
  run: () => refreshRuns(),
  shouldPoll: () => runs.value.some(isActive),
});

async function refreshRuns() {
  const requestId = ++pollRequest;
  await list.refresh();
  if (requestId !== pollRequest) return undefined;
  await refreshActiveEvents(runs.value.find(isActive) || runs.value[0]);
  poller.reschedule();
  return listSignature();
}

// Filters live in the URL: reload, share and back all land on the same list.
async function changeFilters(next) {
  if (list.selectionCount.value) list.selectionNotice.value = '筛选或视图已变化，之前的选择已清空。';
  batchResult.value = null;
  batchError.value = '';
  list.applyFilters(next);
  await router.replace({ query: { ...route.query, ...clearedFilterQuery(), ...filtersToQuery(list.filters) } });
  await reloadList();
}

// A full reload (first visit, or the filters changed) instead of a poll that keeps the loaded pages.
async function reloadList() {
  const requestId = ++pollRequest;
  await list.load();
  if (requestId !== pollRequest) return;
  await refreshActiveEvents(runs.value.find(isActive) || runs.value[0]);
  poller.reschedule();
}

function clearedFilterQuery() {
  return { q: undefined, lifecycle: undefined, format: undefined, direction: undefined, domain: undefined, archived: undefined, sort: undefined, order: undefined };
}

function resetFilters() {
  return changeFilters({});
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
  renaming.value = {
    id: run.id,
    value: run.display_name || run.filename || '',
    original: run.display_name || '',
    version: run.name_version ?? 0,
    saving: false,
    error: '',
  };
  await nextTick();
  const input = Array.isArray(renameInput.value) ? renameInput.value[0] : renameInput.value;
  input?.focus?.();
  input?.select?.();
}

function cancelRename() {
  const id = renaming.value?.id;
  renaming.value = null;
  nextTick(() => document.querySelector(`[data-run-id="${id}"]`)?.focus?.({ preventScroll: true }));
}

// `reset === true` goes back to the original file name; a keyboard event arrives as a non-boolean.
async function commitRename(reset = false) {
  const edit = renaming.value;
  if (!edit || edit.saving) return;
  const back = reset === true;
  const name = edit.value.trim();
  if (!back && name === edit.original) { cancelRename(); return; }
  if (!back && !name) { edit.error = '任务名称不能为空；要使用原文件名请选择“恢复为原文件名”'; return; }
  if (!back && name.length > 120) { edit.error = '任务名称最长 120 个字符'; return; }
  edit.saving = true;
  edit.error = '';
  try {
    const updated = await api.patchRun(
      edit.id,
      back ? { reset_display_name: true } : { display_name: name },
      { nameVersion: edit.version },
    );
    list.patchItem(edit.id, { display_name: updated.display_name, name_version: updated.name_version });
    cancelRename();
  } catch (error) {
    edit.saving = false;
    const detail = error.payload?.detail;
    if (error.status === 409 && detail?.code === 'NAME_CONFLICT') {
      // Someone renamed it elsewhere: show their name, keep the person's text, and let them decide.
      edit.version = detail.current_version;
      edit.original = detail.current_name || '';
      edit.error = `该任务刚刚被改名为「${detail.current_name || '原文件名'}」。再次保存会覆盖它。`;
      list.patchItem(edit.id, { display_name: detail.current_name, name_version: detail.current_version });
    } else {
      edit.error = error.message || '重命名失败';
    }
  }
}

async function deleteRun(run) {
  const confirmed = await confirmDialog({
    title: `把“${rowName(run)}”移入回收站？`,
    body: '30 天内可以在“回收站”里恢复；到期前不会删除任何文件。',
    confirmLabel: '移入回收站',
    danger: true,
  });
  if (!confirmed) return;
  try {
    await api.deleteRun(run.id);
    const deletedSelectedPreflight = preflight.value?.id === run.preflight_id;
    if (deletedSelectedPreflight) {
      preflight.value = null;
      uploadError.value = false;
      uploadMessage.value = '任务已移入回收站。这份预检对应的任务不在列表里了，请重新开始预检。';
    } else {
      uploadError.value = false;
      uploadMessage.value = '已移入回收站，30 天内可在“回收站”里恢复。';
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
  poller.start();
  loadUploadLimits(); // in the background: the box works with the built-in list until the server answers
  await sessionStore.load();
  await restoreWorkbenchSession(sessionStore.user);
  defaultsSnapshot.value = { ...workbenchState };
  // A pre-check that already has a task cannot start another one, so it is not restored as "ready".
  if (preflight.value === null && restoredPreflight.value?.state === 'ready' && !restoredPreflight.value.used_by_run_id) {
    preflight.value = restoredPreflight.value;
    uploadMessage.value = '已恢复上次预检结果，可直接开始翻译。';
  }
  const before = JSON.stringify(filtersToQuery(list.filters));
  list.applyFilters(filtersFromQuery(route.query));
  const changed = before !== JSON.stringify(filtersToQuery(list.filters));
  // Coming back from a task: show what was there, put the person back where they were, then refresh.
  const restoredScroll = list.loaded.value && !changed && listView.openedId;
  if (list.loaded.value && !changed) await refreshRuns();
  else await reloadList();
  if (restoredScroll) {
    await nextTick();
    window.scrollTo?.(0, listView.scrollY);
    document.querySelector(`[data-run-id="${listView.openedId}"]`)?.focus?.({ preventScroll: true });
    listView.openedId = '';
  }
});
onUnmounted(() => {
  poller.stop();
  window.removeEventListener('dragover', ignoreStrayFileDrop);
  window.removeEventListener('drop', ignoreStrayFileDrop);
});
</script>

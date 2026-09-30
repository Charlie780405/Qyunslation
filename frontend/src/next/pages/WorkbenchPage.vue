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
          <label class="qy-dropzone" :class="{ 'is-selected': selectedFile }" for="workbench-file">
            <input id="workbench-file" ref="fileInput" type="file" class="qy-visually-hidden" accept=".pdf,.docx,.pptx,.txt,.md" @change="selectFile" />
            <DocumentArrowUpIcon aria-hidden="true" />
            <strong>{{ selectedFile ? selectedFile.name : '拖放文件到这里，或点击选择' }}</strong>
            <span>{{ selectedFile ? formatSize(selectedFile.size) : '支持 PDF、DOCX、PPTX、TXT、Markdown' }}</span>
          </label>
          <div v-if="uploadMessage" class="qy-callout" :class="uploadError ? 'qy-callout-warning' : 'qy-callout-info'" role="status">
            <InformationCircleIcon aria-hidden="true" /><span>{{ uploadMessage }}</span>
          </div>
          <div v-if="preflight" class="qy-preflight-card" aria-live="polite">
            <div><strong>{{ preflight.filename }}</strong><span>{{ preflight.format?.toUpperCase() }} · {{ formatSize(preflight.size_bytes) }} · SHA-256 已记录</span></div>
            <span class="qy-status-badge" :class="preflight.state === 'ready' ? 'is-ready' : 'is-pending'">{{ preflight.state === 'ready' ? '预检通过' : '需要处理' }}</span>
            <button class="qy-primary-button" type="button" :disabled="startingRun || preflight.state !== 'ready'" @click="startTranslation">
              <ArrowPathIcon v-if="startingRun" class="qy-spin" aria-hidden="true" />
              <PlayIcon v-else aria-hidden="true" />
              {{ startingRun ? '正在创建任务…' : '确认并开始翻译' }}
            </button>
          </div>
          <div class="qy-panel-actions">
            <button class="qy-primary-button" type="button" :disabled="!selectedFile || uploading" @click="startPreflight">
              <ArrowPathIcon v-if="uploading" class="qy-spin" aria-hidden="true" />
              <MagnifyingGlassIcon v-else aria-hidden="true" />
              {{ uploading ? '正在预检…' : '开始预检' }}
            </button>
            <span class="qy-inline-hint">不会自动开始翻译</span>
          </div>
        </div>

        <div class="qy-panel qy-task-panel">
          <div class="qy-panel-heading">
            <div><span class="qy-step-index qy-step-muted">02</span><div><h2>最近任务</h2><p>离开页面后，任务仍会在服务端继续运行。</p></div></div>
            <button class="qy-link-button" type="button" @click="refreshRuns">刷新</button>
          </div>
          <div v-if="runs.length" class="qy-task-list">
            <article v-for="run in runs" :key="run.id" class="qy-task-row">
              <div class="qy-task-file-icon"><DocumentTextIcon aria-hidden="true" /></div>
              <div class="qy-task-details"><strong>{{ run.filename || run.file_name || '未命名文档' }}</strong><span>{{ run.status || '待处理' }} · {{ run.updated_at || '刚刚' }}</span></div>
              <ChevronRightIcon aria-hidden="true" />
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
          <h2>一次任务，五个可复核阶段</h2>
          <ol class="qy-flow-list">
            <li class="is-current"><span>01</span><div><strong>文件预检</strong><small>识别格式、页数与风险</small></div></li>
            <li><span>02</span><div><strong>翻译处理</strong><small>按文档对象保留结构</small></div></li>
            <li><span>03</span><div><strong>QA 与术语</strong><small>发现高风险不一致</small></div></li>
            <li><span>04</span><div><strong>人工复核</strong><small>只编辑译文版本</small></div></li>
            <li><span>05</span><div><strong>受控导出</strong><small>通过门禁后生成正式稿</small></div></li>
          </ol>
        </div>
        <div v-if="showAdvanced" class="qy-panel qy-settings-card">
          <div class="qy-panel-heading"><div><h2>本次任务参数</h2><p>开始翻译后将固定为任务快照。</p></div><LockClosedIcon aria-hidden="true" /></div>
          <label class="qy-field"><span>语言方向</span><select v-model="settings.direction"><option>English → 简体中文</option><option>简体中文 → English</option></select></label>
          <label class="qy-field"><span>文档类型</span><select v-model="settings.profile"><option>临床研究文档</option><option>监管申报材料</option><option>通用医药文档</option></select></label>
          <label class="qy-check-field"><input v-model="settings.bilingual" type="checkbox" /><span>生成源译对照稿</span></label>
        </div>
      </aside>
    </div>
  </AppShell>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
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

const selectedFile = ref(null);
const fileInput = ref(null);
const uploadMessage = ref('');
const uploadError = ref(false);
const uploading = ref(false);
const showAdvanced = ref(false);
const runs = ref([]);
const preflight = ref(null);
const startingRun = ref(false);
const settings = reactive({ direction: 'English → 简体中文', profile: '临床研究文档', bilingual: true });

function selectFile(event) {
  selectedFile.value = event.target.files?.[0] || null;
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
  uploading.value = true;
  uploadError.value = false;
  uploadMessage.value = '';
  try {
    preflight.value = await api.uploadPreflight(selectedFile.value, { direction: settings.direction, profile: settings.profile });
    uploadMessage.value = preflight.value.state === 'ready'
      ? '预检已完成。请确认参数后再开始翻译。'
      : '预检发现风险，请先处理阻断项。';
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.status === 404 ? '预检服务正在接入，当前仅完成工作台界面预览。' : error.message;
  } finally {
    uploading.value = false;
  }
}

async function startTranslation() {
  if (!preflight.value || preflight.value.state !== 'ready') return;
  startingRun.value = true;
  uploadError.value = false;
  try {
    const key = `preflight:${preflight.value.id}:${settings.direction}:${settings.profile}:${settings.bilingual}`;
    await api.createTranslationRun({
      preflight_id: preflight.value.id,
      direction: settings.direction,
      profile: settings.profile,
      bilingual: settings.bilingual,
    }, key);
    uploadMessage.value = '翻译任务已创建，服务端会继续处理。';
    await refreshRuns();
  } catch (error) {
    uploadError.value = true;
    uploadMessage.value = error.message || '翻译任务创建失败';
  } finally {
    startingRun.value = false;
  }
}

async function refreshRuns() {
  try {
    const response = await api.listRuns();
    runs.value = Array.isArray(response) ? response : response.items || [];
  } catch {
    runs.value = [];
  }
}

onMounted(refreshRuns);
</script>

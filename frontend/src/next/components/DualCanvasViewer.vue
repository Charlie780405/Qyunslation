<template>
  <section class="qy-viewer" role="region" aria-label="源译对照预览" :data-layout="layout">
    <div class="qy-viewer-controls" role="toolbar" aria-label="预览控制">
      <div class="qy-viewer-group" role="group" aria-label="页码">
        <button type="button" class="qy-icon-button" aria-label="上一页" :disabled="page <= 1" @click="goTo(page - 1)">‹</button>
        <label class="qy-viewer-page">
          <span class="qy-sr-only">当前页码</span>
          <input
            type="number"
            min="1"
            :max="totalPages || 1"
            :value="page"
            aria-label="当前页码"
            @change="onPageInput"
          />
          <span aria-hidden="true">/ {{ totalPages || '—' }}</span>
        </label>
        <button type="button" class="qy-icon-button" aria-label="下一页" :disabled="totalPages > 0 && page >= totalPages" @click="goTo(page + 1)">›</button>
      </div>
      <div class="qy-viewer-group" role="group" aria-label="缩放">
        <button type="button" class="qy-icon-button" aria-label="缩小" @click="zoomBy(-ZOOM_STEP)">−</button>
        <output class="qy-viewer-zoom" aria-label="当前缩放">{{ zoomLabel }}</output>
        <button type="button" class="qy-icon-button" aria-label="放大" @click="zoomBy(ZOOM_STEP)">+</button>
        <button type="button" class="qy-secondary-button" aria-label="适应宽度" :aria-pressed="zoom === 'fit'" @click="$emit('update:zoom', 'fit')">适宽</button>
      </div>
      <button
        v-if="layout === 'desktop'"
        type="button"
        class="qy-secondary-button"
        :aria-pressed="syncScroll"
        aria-label="同步滚动"
        @click="$emit('update:syncScroll', !syncScroll)"
      >{{ syncScroll ? '同步滚动：开' : '同步滚动：关' }}</button>
    </div>

    <div v-if="layout === 'tablet'" class="qy-viewer-tabs" role="tablist" aria-label="源译页签">
      <button
        v-for="tab in SIDES"
        :id="`qy-tab-${tab.side}`"
        :key="tab.side"
        type="button"
        role="tab"
        class="qy-viewer-tab"
        :aria-selected="activeSide === tab.side"
        :aria-controls="`qy-panel-${tab.side}`"
        :aria-label="`切换到${tab.label}`"
        @click="activeSide = tab.side"
      >{{ tab.label }}</button>
    </div>
    <div v-else-if="layout === 'phone'" class="qy-viewer-tabs" role="group" aria-label="源译切换">
      <button
        v-for="tab in SIDES"
        :key="tab.side"
        type="button"
        class="qy-viewer-tab"
        :aria-pressed="activeSide === tab.side"
        :aria-label="`显示${tab.label}`"
        @click="activeSide = tab.side"
      >{{ tab.label }}</button>
    </div>

    <div class="qy-viewer-canvases">
      <div
        v-for="tab in SIDES"
        v-show="layout === 'desktop' || activeSide === tab.side"
        :id="`qy-panel-${tab.side}`"
        :key="tab.side"
        class="qy-viewer-slot"
        :role="layout === 'tablet' ? 'tabpanel' : undefined"
        :aria-labelledby="layout === 'tablet' ? `qy-tab-${tab.side}` : undefined"
      >
        <PdfPane
          :ref="(el) => setPaneRef(tab.side, el)"
          :side="tab.side"
          :label="tab.label"
          :content="contents[tab.side]"
          :page="page"
          :zoom="zoom"
          :active="layout === 'desktop' || activeSide === tab.side"
          @page-change="(n) => onPaneRaisedPage(tab.side, n)"
          @scroll-ratio="(r) => onPaneScroll(tab.side, r)"
          @retry="load(tab.side)"
        />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, markRaw, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { api } from '../api.js';
import { loadPdfjs } from '../lib/pdfjs.js';
import { MAX_ZOOM, MIN_ZOOM, ZOOM_STEP, clampZoom } from '../stores/runDetail.js';
import PdfPane from './PdfPane.vue';

const props = defineProps({
  runId: { type: String, required: true },
  page: { type: Number, default: 1 },
  zoom: { type: [Number, String], default: 'fit' },
  syncScroll: { type: Boolean, default: true },
  refreshKey: { type: String, default: '' },
});
const emit = defineEmits(['update:page', 'update:zoom', 'update:syncScroll']);

const SIDES = [
  { side: 'source', label: '源文' },
  { side: 'translated', label: '译文' },
];

const EMPTY_MESSAGES = {
  source: '源文件预览尚不可用',
  translated: '译文预览尚未生成',
};

const contents = reactive({
  source: { status: 'loading' },
  translated: { status: 'loading' },
});
const panes = {};
const layout = ref('desktop');
const activeSide = ref('source');
const generation = { source: 0, translated: 0 };
let internalPage = props.page;
let scrollDriver = null;
let mediaCleanup = [];

const totalPages = computed(() => Math.max(
  0,
  ...SIDES.map(({ side }) => (contents[side].status === 'ready' ? contents[side].doc.numPages : 0)),
));
const zoomLabel = computed(() => (props.zoom === 'fit' ? '适宽' : `${Math.round(Number(props.zoom) * 100)}%`));

function setPaneRef(side, el) {
  if (el) panes[side] = el;
  else delete panes[side];
}

function releaseContent(content) {
  if (content?.doc?.destroy) content.doc.destroy().catch(() => {});
  if (content?.imageUrl) URL.revokeObjectURL(content.imageUrl);
}

function setContent(side, content) {
  releaseContent(contents[side]);
  contents[side] = content;
}

async function load(side) {
  const token = ++generation[side];
  const url = api.previewUrl(props.runId, side);
  if (contents[side].status !== 'ready') contents[side] = { status: 'loading' };
  try {
    const response = await fetch(url, { credentials: 'same-origin' });
    if (token !== generation[side]) return;
    if (response.status === 404 || response.status === 409) {
      setContent(side, { status: 'empty', message: EMPTY_MESSAGES[side] });
      return;
    }
    if (!response.ok) {
      setContent(side, { status: 'error', message: `${side === 'source' ? '源文' : '译文'}预览加载失败（${response.status}）` });
      return;
    }
    const type = (response.headers.get('content-type') || '').toLowerCase();
    if (type.includes('pdf')) {
      const bytes = new Uint8Array(await response.arrayBuffer());
      const pdfjs = await loadPdfjs();
      const doc = await pdfjs.getDocument({ data: bytes }).promise;
      if (token !== generation[side]) {
        doc.destroy().catch(() => {});
        return;
      }
      setContent(side, { status: 'ready', doc: markRaw(doc) });
    } else if (type.startsWith('image/')) {
      const blob = await response.blob();
      if (token !== generation[side]) return;
      setContent(side, { status: 'image', imageUrl: URL.createObjectURL(blob) });
    } else {
      setContent(side, {
        status: 'unsupported',
        message: '该格式暂不支持内嵌预览',
        downloadUrl: url,
      });
    }
  } catch (error) {
    if (token !== generation[side]) return;
    setContent(side, { status: 'error', message: `预览加载失败：${error?.message || '未知错误'}` });
  }
}

function scrollAll(n) {
  for (const pane of Object.values(panes)) pane.scrollToPage?.(n);
}

function goTo(n) {
  const max = totalPages.value || n;
  const target = Math.min(Math.max(1, n), Math.max(1, max));
  internalPage = target;
  emit('update:page', target);
  scrollAll(target);
}

function onPageInput(event) {
  const value = Math.floor(Number(event.target.value));
  if (!Number.isFinite(value)) {
    event.target.value = props.page;
    return;
  }
  goTo(value);
  event.target.value = Math.min(Math.max(1, value), Math.max(1, totalPages.value || value));
}

function zoomBy(delta) {
  const current = props.zoom === 'fit' ? (panes[activeSide.value]?.currentScale ?? panes.source?.currentScale ?? 1) : Number(props.zoom);
  emit('update:zoom', clampZoom(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current + delta))));
}

function onPaneRaisedPage(side, n) {
  scrollDriver = side;
  if (n === internalPage) return;
  internalPage = n;
  emit('update:page', n);
}

function onPaneScroll(side, ratio) {
  scrollDriver = side;
  if (!props.syncScroll || layout.value !== 'desktop') return;
  for (const other of SIDES) {
    if (other.side !== side) panes[other.side]?.setScrollRatio?.(ratio);
  }
}

function setupMedia() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
  const desktop = window.matchMedia('(min-width: 1024px)');
  const tablet = window.matchMedia('(min-width: 640px)');
  const apply = () => {
    layout.value = desktop.matches ? 'desktop' : tablet.matches ? 'tablet' : 'phone';
  };
  apply();
  for (const query of [desktop, tablet]) {
    if (query.addEventListener) {
      query.addEventListener('change', apply);
      mediaCleanup.push(() => query.removeEventListener('change', apply));
    } else if (query.addListener) {
      query.addListener(apply);
      mediaCleanup.push(() => query.removeListener(apply));
    }
  }
}

watch(() => props.page, (value) => {
  if (value !== internalPage) {
    internalPage = value;
    scrollAll(value);
  }
});

watch(totalPages, (total) => {
  if (total > 0 && props.page > total) goTo(total);
});

watch(() => props.runId, () => {
  load('source');
  load('translated');
});

watch(() => props.refreshKey, () => {
  for (const { side } of SIDES) {
    if (contents[side].status !== 'ready' && contents[side].status !== 'image') load(side);
  }
});

onMounted(() => {
  setupMedia();
  load('source');
  load('translated');
});

onBeforeUnmount(() => {
  generation.source += 1;
  generation.translated += 1;
  mediaCleanup.forEach((fn) => fn());
  mediaCleanup = [];
  SIDES.forEach(({ side }) => releaseContent(contents[side]));
});

defineExpose({ goTo, layout, scrollDriver: () => scrollDriver });
</script>

<style scoped>
.qy-viewer { display: grid; grid-template-rows: auto auto 1fr; gap: .5rem; min-width: 0; }
.qy-viewer-controls { display: flex; flex-wrap: wrap; gap: .5rem 1rem; align-items: center; position: sticky; top: 0; z-index: 2; background: #fff; padding: .4rem .5rem; border: 1px solid var(--qy-border, #d6dce3); }
.qy-viewer-group { display: inline-flex; align-items: center; gap: .35rem; }
.qy-viewer-page { display: inline-flex; align-items: center; gap: .3rem; }
.qy-viewer-page input { width: 4rem; padding: .2rem .3rem; }
.qy-viewer-zoom { min-width: 3.5rem; text-align: center; }
.qy-icon-button { min-width: 2.25rem; min-height: 2.25rem; border: 1px solid var(--qy-border, #d6dce3); background: #fff; cursor: pointer; }
.qy-icon-button:disabled { opacity: .5; cursor: not-allowed; }
.qy-viewer-tabs { display: flex; gap: .25rem; }
.qy-viewer-tab { flex: 1; min-height: 2.5rem; border: 1px solid var(--qy-border, #d6dce3); background: #fff; cursor: pointer; }
.qy-viewer-tab[aria-selected='true'], .qy-viewer-tab[aria-pressed='true'] { background: #1f3a5f; color: #fff; }
.qy-viewer-canvases { display: grid; grid-template-columns: 1fr; gap: .5rem; min-height: 0; height: min(78vh, 900px); }
.qy-viewer-slot { min-height: 0; display: grid; }
.qy-viewer[data-layout='desktop'] .qy-viewer-canvases { grid-template-columns: 1fr 1fr; }
.qy-sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>

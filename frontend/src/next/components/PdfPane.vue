<template>
  <section class="qy-pane" role="region" :aria-label="`${label}画布`" :data-side="side">
    <header class="qy-pane-head">
      <strong>{{ label }}</strong>
      <small v-if="numPages">{{ numPages }} 页</small>
    </header>
    <div
      ref="scroller"
      class="qy-pane-scroll"
      tabindex="0"
      :aria-label="`${label}页面滚动区域`"
      @scroll.passive="onScroll"
    >
      <p v-if="content.status === 'loading'" class="qy-pane-state" role="status">正在加载{{ label }}…</p>
      <div v-else-if="content.status === 'empty' || content.status === 'error' || content.status === 'unsupported'" class="qy-pane-state" role="status">
        <p>{{ content.message }}</p>
        <button
          v-if="content.status !== 'unsupported'"
          class="qy-secondary-button"
          type="button"
          :aria-label="`重新加载${label}预览`"
          @click="$emit('retry')"
        >重新加载</button>
        <a
          v-if="content.status === 'unsupported' && content.downloadUrl"
          class="qy-link-button"
          :href="content.downloadUrl"
          target="_blank"
          rel="noopener"
        >打开原始预览</a>
      </div>
      <div v-else-if="content.status === 'image'" class="qy-pane-image">
        <img :src="content.imageUrl" :alt="`${label}图片预览`" :style="imageStyle" />
      </div>
      <div v-else class="qy-pages">
        <div
          v-for="n in numPages"
          :key="n"
          :ref="(el) => setPageEl(n, el)"
          class="qy-page"
          :data-page="n"
          :style="pageStyle(n)"
        >
          <canvas :ref="(el) => setCanvasEl(n, el)" :aria-label="`${label}第 ${n} 页`" role="img"></canvas>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';

const props = defineProps({
  side: { type: String, required: true },
  label: { type: String, required: true },
  content: { type: Object, required: true },
  page: { type: Number, default: 1 },
  zoom: { type: [Number, String], default: 'fit' },
  active: { type: Boolean, default: true },
});
const emit = defineEmits(['page-change', 'scroll-ratio', 'scale', 'retry']);

const scroller = ref(null);
const containerWidth = ref(0);
const baseSizes = reactive({});
const pageEls = new Map();
const canvasEls = new Map();
const rendered = new Map();
const inflight = new Map();
let epoch = 0;
const visible = new Set();
let observer = null;
let resizeObserver = null;
let suppressScrollUntil = 0;
let destroyed = false;

const doc = computed(() => (props.content.status === 'ready' ? props.content.doc : null));
const numPages = computed(() => (doc.value ? doc.value.numPages : 0));
const baseWidth = computed(() => baseSizes[1]?.[0] || 612);

const scale = computed(() => {
  if (props.zoom === 'fit') {
    const width = containerWidth.value;
    if (!width) return 1;
    return Math.max(0.25, Math.min(4, (width - 24) / baseWidth.value));
  }
  return Number(props.zoom) || 1;
});
const scaleKey = computed(() => scale.value.toFixed(3));
const imageStyle = computed(() => (
  props.zoom === 'fit' ? { maxWidth: '100%' } : { width: `${Math.round(props.zoom * 100)}%`, maxWidth: 'none' }
));

function pageStyle(n) {
  const size = baseSizes[n] || baseSizes[1] || [612, 792];
  return {
    width: `${Math.floor(size[0] * scale.value)}px`,
    height: `${Math.floor(size[1] * scale.value)}px`,
  };
}

function setPageEl(n, el) {
  const previous = pageEls.get(n);
  if (previous && previous !== el && observer) observer.unobserve(previous);
  if (el) {
    pageEls.set(n, el);
    if (observer) observer.observe(el);
  } else {
    pageEls.delete(n);
  }
}
function setCanvasEl(n, el) {
  if (el) canvasEls.set(n, el);
  else canvasEls.delete(n);
}

function cancelAll() {
  epoch += 1;
  for (const job of inflight.values()) {
    try { job.task?.cancel(); } catch { /* already finished */ }
  }
  inflight.clear();
  rendered.clear();
}

async function renderPage(n) {
  const currentDoc = doc.value;
  if (!currentDoc || !canvasEls.get(n) || !props.active) return;
  const key = scaleKey.value;
  if (rendered.get(n) === key || inflight.get(n)?.key === key) return;
  const job = { key, task: null };
  const myEpoch = epoch;
  inflight.set(n, job);
  const stale = () => destroyed || myEpoch !== epoch || doc.value !== currentDoc;
  try {
    const pdfPage = await currentDoc.getPage(n);
    const canvas = canvasEls.get(n);
    if (stale() || !canvas) return;
    const unit = pdfPage.getViewport({ scale: 1 });
    baseSizes[n] = [unit.width, unit.height];
    const viewport = pdfPage.getViewport({ scale: scale.value });
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.floor(viewport.width * ratio));
    canvas.height = Math.max(1, Math.floor(viewport.height * ratio));
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;
    const context = canvas.getContext('2d');
    if (!context) return;
    job.task = pdfPage.render({
      canvasContext: context,
      viewport,
      transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
    });
    await job.task.promise;
    if (!stale()) rendered.set(n, key);
  } catch (error) {
    if (error?.name !== 'RenderingCancelledException') console.warn('pdf page render failed', n, error);
  } finally {
    if (inflight.get(n) === job) inflight.delete(n);
  }
}

function targetPages() {
  const wanted = new Set();
  const count = numPages.value;
  if (!count) return wanted;
  const current = Math.min(Math.max(props.page, 1), count);
  for (let n = current - 1; n <= current + 1; n += 1) {
    if (n >= 1 && n <= count) wanted.add(n);
  }
  for (const n of visible) wanted.add(n);
  return wanted;
}

function renderWanted() {
  for (const n of targetPages()) renderPage(n);
}

function pageTop(n) {
  const el = pageEls.get(n);
  return el ? el.offsetTop : 0;
}

function scrollToPage(n) {
  const el = scroller.value;
  if (!el || !pageEls.get(n)) return;
  suppressScrollUntil = Date.now() + 120;
  el.scrollTop = Math.max(0, pageTop(n) - 8);
}

function detectPage() {
  const el = scroller.value;
  if (!el || !numPages.value) return 1;
  const probe = el.scrollTop + el.clientHeight * 0.25;
  let found = 1;
  for (let n = 1; n <= numPages.value; n += 1) {
    if (pageTop(n) <= probe) found = n;
    else break;
  }
  return found;
}

function onScroll() {
  const el = scroller.value;
  if (!el) return;
  if (Date.now() < suppressScrollUntil) return;
  const max = el.scrollHeight - el.clientHeight;
  emit('scroll-ratio', max > 0 ? el.scrollTop / max : 0);
  const detected = detectPage();
  if (detected !== props.page) emit('page-change', detected);
}

function setScrollRatio(ratio) {
  const el = scroller.value;
  if (!el) return;
  const max = el.scrollHeight - el.clientHeight;
  if (max <= 0) return;
  suppressScrollUntil = Date.now() + 120;
  el.scrollTop = ratio * max;
}

function updateWidth() {
  const width = scroller.value?.clientWidth || 0;
  if (width !== containerWidth.value) containerWidth.value = width;
}

onMounted(() => {
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const n = Number(entry.target.dataset.page);
        if (entry.isIntersecting) visible.add(n);
        else visible.delete(n);
      }
      renderWanted();
    }, { root: scroller.value, rootMargin: '300px 0px' });
    for (const el of pageEls.values()) observer.observe(el);
  }
  if (typeof ResizeObserver !== 'undefined' && scroller.value) {
    resizeObserver = new ResizeObserver(updateWidth);
    resizeObserver.observe(scroller.value);
  }
  updateWidth();
  renderWanted();
});

onBeforeUnmount(() => {
  destroyed = true;
  if (observer) observer.disconnect();
  if (resizeObserver) resizeObserver.disconnect();
  cancelAll();
});

watch(doc, async () => {
  cancelAll();
  visible.clear();
  for (const key of Object.keys(baseSizes)) delete baseSizes[key];
  await nextTick();
  if (doc.value) {
    try {
      const first = await doc.value.getPage(1);
      const unit = first.getViewport({ scale: 1 });
      baseSizes[1] = [unit.width, unit.height];
    } catch (error) {
      console.warn('pdf first page size failed', error);
    }
  }
  await nextTick();
  updateWidth();
  scrollToPage(props.page);
  renderWanted();
});

watch(scaleKey, async () => {
  cancelAll();
  emit('scale', scale.value);
  await nextTick();
  renderWanted();
});

watch(() => props.page, () => renderWanted());

watch(() => props.active, async (value) => {
  if (!value) return;
  await nextTick();
  updateWidth();
  renderWanted();
});

defineExpose({ scrollToPage, setScrollRatio, detectPage, currentScale: scale });
</script>

<style scoped>
.qy-pane { display: flex; flex-direction: column; min-width: 0; min-height: 0; border: 1px solid var(--qy-border, #d6dce3); background: #eef1f5; }
.qy-pane-head { display: flex; justify-content: space-between; align-items: baseline; padding: .4rem .75rem; background: #fff; border-bottom: 1px solid var(--qy-border, #d6dce3); }
.qy-pane-head small { color: #4a5565; }
.qy-pane-scroll { flex: 1; min-height: 0; overflow: auto; padding: .75rem; }
.qy-pages { display: grid; gap: .75rem; justify-content: center; }
.qy-page { background: #fff; box-shadow: 0 1px 4px rgba(0, 0, 0, .18); margin: 0 auto; }
.qy-page canvas { display: block; }
.qy-pane-state { display: grid; gap: .5rem; justify-items: center; padding: 2rem 1rem; color: #3b4452; text-align: center; }
.qy-pane-image img { display: block; margin: 0 auto; }
</style>

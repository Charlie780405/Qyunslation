<template>
  <div class="qy-list-toolbar" role="search">
    <div class="qy-list-search">
      <MagnifyingGlassIcon aria-hidden="true" />
      <input
        :value="draft"
        type="search"
        class="qy-input"
        data-run-search
        placeholder="搜索任务名称或文件名"
        aria-label="搜索任务"
        maxlength="200"
        @input="onInput"
        @keydown.enter.prevent="flush"
      />
    </div>
    <select class="qy-input" data-run-sort :value="sortKey" aria-label="排序" @change="onSort($event.target.value)">
      <option v-for="option in SORTS" :key="option.key" :value="option.key">{{ option.label }}</option>
    </select>
    <select class="qy-input" data-run-archived :value="modelValue.archived" aria-label="归档范围" @change="emitChange({ archived: $event.target.value })">
      <option value="active">未归档</option>
      <option value="archived">仅已归档</option>
      <option value="all">全部</option>
    </select>
    <select class="qy-input" data-run-format :value="modelValue.format" aria-label="文件格式" @change="emitChange({ format: $event.target.value })">
      <option value="">全部格式</option>
      <option v-for="format in FORMATS" :key="format" :value="format">{{ format.toUpperCase() }}</option>
    </select>
    <button v-if="active" class="qy-link-button" type="button" data-run-clear @click="clear">清除筛选</button>
    <div class="qy-list-chips" role="group" aria-label="按阶段筛选">
      <button
        v-for="name in LIFECYCLES"
        :key="name"
        type="button"
        class="qy-chip"
        :class="{ 'is-on': modelValue.lifecycle.includes(name) }"
        :aria-pressed="modelValue.lifecycle.includes(name)"
        :data-lifecycle-chip="name"
        @click="toggleLifecycle(name)"
      >
        {{ LIFECYCLE_LABELS[name] }}<span v-if="facets.lifecycle?.[name]" class="qy-chip-count">{{ facets.lifecycle[name] }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { MagnifyingGlassIcon } from '@heroicons/vue/24/outline';
import { LIFECYCLE_LABELS } from '../labels.js';
import { hasActiveFilters } from '../stores/runs.js';

const props = defineProps({
  modelValue: { type: Object, required: true },
  facets: { type: Object, default: () => ({ lifecycle: {}, total: 0 }) },
  debounceMs: { type: Number, default: 300 },
});
const emit = defineEmits(['update:modelValue']);

const SORTS = [
  { key: 'created:desc', label: '最新创建' },
  { key: 'created:asc', label: '最早创建' },
  { key: 'updated:desc', label: '最近更新' },
  { key: 'name:asc', label: '名称 A→Z' },
  { key: 'name:desc', label: '名称 Z→A' },
];
const FORMATS = ['pdf', 'docx', 'pptx', 'txt', 'md', 'png', 'jpg'];
const LIFECYCLES = Object.keys(LIFECYCLE_LABELS);

const draft = ref(props.modelValue.q || '');
let timer;

const sortKey = computed(() => `${props.modelValue.sort}:${props.modelValue.order}`);
const active = computed(() => hasActiveFilters(props.modelValue) || Boolean(draft.value));

// The URL (or "clear filters") can change q from outside; keep the box in step with it.
watch(() => props.modelValue.q, (value) => {
  if ((value || '') !== draft.value.trim()) draft.value = value || '';
});

function emitChange(patch) {
  emit('update:modelValue', { ...props.modelValue, lifecycle: [...props.modelValue.lifecycle], ...patch });
}

function onInput(event) {
  draft.value = event.target.value;
  window.clearTimeout(timer);
  timer = window.setTimeout(flush, props.debounceMs);
}

function flush() {
  window.clearTimeout(timer);
  const next = draft.value.trim();
  if (next !== (props.modelValue.q || '')) emitChange({ q: next });
}

function onSort(value) {
  const [sort, order] = value.split(':');
  emitChange({ sort, order });
}

function toggleLifecycle(name) {
  const current = props.modelValue.lifecycle;
  emitChange({ lifecycle: current.includes(name) ? current.filter((entry) => entry !== name) : [...current, name] });
}

function clear() {
  window.clearTimeout(timer);
  draft.value = '';
  emit('update:modelValue', {
    q: '', lifecycle: [], format: '', direction: '', domain: '', archived: 'active', sort: 'created', order: 'desc',
  });
}

onBeforeUnmount(() => window.clearTimeout(timer));
</script>

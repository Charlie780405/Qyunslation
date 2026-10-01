<template>
  <aside class="qy-inspector" role="complementary" aria-label="对象检查器">
    <section aria-labelledby="qy-qa-heading">
      <h2 id="qy-qa-heading">QA 项 <small>({{ items.length }})</small></h2>
      <ul v-if="items.length" class="qy-qa-list">
        <li v-for="item in items" :key="item.id" :data-severity="item.severity">
          <button
            type="button"
            class="qy-qa-item"
            :aria-pressed="selectedId === keyOf(item)"
            :aria-label="`检查 QA 项 ${item.code}：${item.message}`"
            @click="$emit('select', selectedId === keyOf(item) ? '' : keyOf(item))"
          >
            <strong>{{ item.severity }}</strong>
            <span>{{ item.code }}</span>
            <span class="qy-qa-message">{{ item.message }}</span>
            <em v-if="item.resolved" class="qy-qa-resolved">已解决</em>
          </button>
        </li>
      </ul>
      <p v-else class="qy-muted">暂无 QA 项</p>
    </section>

    <section aria-labelledby="qy-object-heading" class="qy-object-detail">
      <h2 id="qy-object-heading">对象详情</h2>
      <p v-if="!selectedId" class="qy-muted">选择一个 QA 项以查看对应对象。</p>
      <p v-else-if="!matches.length" class="qy-muted" role="status">
        未找到对象 {{ selectedId }} 的 QA 项，可能已被重新生成。
        <button type="button" class="qy-link-button" aria-label="清除选中对象" @click="$emit('select', '')">清除选择</button>
      </p>
      <template v-else>
        <dl class="qy-object-fields">
          <dt>对象 ID</dt>
          <dd data-field="object_id">{{ objectIdLabel }}</dd>
          <dt>源文</dt>
          <dd data-field="source">{{ detail.source }}</dd>
          <dt>译文</dt>
          <dd data-field="translation">{{ detail.translation }}</dd>
          <dt>术语命中</dt>
          <dd data-field="terms">{{ detail.terms }}</dd>
          <dt>修订历史</dt>
          <dd data-field="history">{{ detail.history }}</dd>
        </dl>
        <h3>相关 QA</h3>
        <ul class="qy-object-qa">
          <li v-for="item in matches" :key="item.id" :data-severity="item.severity">
            <strong>{{ item.severity }}</strong> {{ item.category || '—' }} · {{ item.code }}
            <p>{{ item.message }}</p>
            <details v-if="hasEvidence(item)">
              <summary>证据</summary>
              <pre>{{ JSON.stringify(item.evidence, null, 2) }}</pre>
            </details>
          </li>
        </ul>
      </template>
    </section>
  </aside>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  items: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
});
defineEmits(['select']);

const UNAVAILABLE = '—';

function keyOf(item) {
  return item.object_id || `qa:${item.id}`;
}

function hasEvidence(item) {
  return item.evidence && typeof item.evidence === 'object' && Object.keys(item.evidence).length > 0;
}

const matches = computed(() => (
  props.selectedId ? props.items.filter((item) => keyOf(item) === props.selectedId) : []
));

const objectIdLabel = computed(() => (
  matches.value.find((item) => item.object_id)?.object_id || UNAVAILABLE
));

function pickText(evidences, keys) {
  for (const evidence of evidences) {
    for (const key of keys) {
      const value = evidence?.[key];
      if (typeof value === 'string' && value.trim()) return value;
    }
  }
  return UNAVAILABLE;
}

function pickTerms(evidences) {
  for (const evidence of evidences) {
    const value = evidence?.terms ?? evidence?.term_hits ?? evidence?.term;
    if (Array.isArray(value) && value.length) {
      return value.map((t) => (typeof t === 'string' ? t : t?.source || t?.term || JSON.stringify(t))).join('、');
    }
    if (typeof value === 'string' && value.trim()) return value;
  }
  return UNAVAILABLE;
}

const detail = computed(() => {
  const evidences = matches.value.map((item) => (hasEvidence(item) ? item.evidence : null)).filter(Boolean);
  return {
    source: pickText(evidences, ['source_text', 'source']),
    translation: pickText(evidences, ['target_text', 'translated_text', 'translation', 'target']),
    terms: pickTerms(evidences),
    history: UNAVAILABLE,
  };
});
</script>

<style scoped>
.qy-inspector { display: grid; gap: 1rem; align-content: start; min-width: 0; }
.qy-inspector h2 { font-size: 1rem; margin: 0 0 .5rem; }
.qy-inspector h3 { font-size: .9rem; margin: .75rem 0 .25rem; }
.qy-qa-list, .qy-object-qa { list-style: none; padding: 0; margin: 0; display: grid; gap: .4rem; }
.qy-qa-item { width: 100%; display: flex; flex-wrap: wrap; gap: .4rem; text-align: left; padding: .45rem .6rem; border: 1px solid var(--qy-border, #d6dce3); background: #fff; cursor: pointer; min-height: 44px; }
.qy-qa-item[aria-pressed='true'] { border-color: #1f3a5f; box-shadow: inset 3px 0 0 #1f3a5f; background: #f1f6fb; }
.qy-qa-message { flex-basis: 100%; color: #2d3744; }
.qy-qa-resolved { color: #1c6b3a; font-style: normal; }
li[data-severity='blocker'] strong { color: #8b1e1e; }
.qy-object-fields { display: grid; grid-template-columns: max-content 1fr; gap: .25rem .75rem; margin: 0; }
.qy-object-fields dt { color: #3b4452; }
.qy-object-fields dd { margin: 0; overflow-wrap: anywhere; }
.qy-object-qa p { margin: .2rem 0; }
.qy-object-qa pre { max-height: 160px; overflow: auto; font-size: .78rem; }
</style>

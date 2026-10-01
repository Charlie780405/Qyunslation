<template>
  <section class="qy-panel qy-review-panel" aria-labelledby="qy-affiliation-review-heading">
    <header>
      <h2 id="qy-affiliation-review-heading">单位译名审核</h2>
      <p>{{ unconfirmed }} 条待确认；确认原机译无需重跑，修改译名后需重新生成。</p>
    </header>
    <p v-if="!items.length" class="qy-muted">未识别到需要确认的研究单位。</p>
    <article v-for="item in items" :key="item.id" class="qy-review-item">
      <strong>{{ item.source_text }}</strong>
      <label>
        <span>确认译名</span>
        <textarea
          v-model="drafts[item.id]"
          rows="2"
          :disabled="item.status === 'approved'"
          :aria-label="`${item.source_text} 的确认译名`"
        />
      </label>
      <div>
        <span>状态：{{ item.status }}</span>
        <button
          v-if="item.status !== 'approved'"
          type="button"
          class="qy-primary-button"
          :aria-label="`确认单位 ${item.source_text}`"
          @click="$emit('decide', item, drafts[item.id])"
        >确认译名</button>
      </div>
    </article>
    <button
      v-if="hasEditedApproval"
      type="button"
      class="qy-primary-button qy-regenerate"
      @click="$emit('apply-corrections')"
    >保存并重新生成</button>
  </section>
</template>

<script setup>
import { computed, reactive, watch } from 'vue';

const props = defineProps({
  items: { type: Array, default: () => [] },
  unconfirmed: { type: Number, default: 0 },
});
defineEmits(['decide', 'apply-corrections']);
const drafts = reactive({});
watch(() => props.items, (items) => {
  items.forEach((item) => {
    drafts[item.id] = item.revised_text || item.machine_text || '';
  });
}, { immediate: true, deep: true });
const hasEditedApproval = computed(() => props.items.some((item) => (
  item.status === 'approved'
  && item.revised_text
  && item.revised_text.trim() !== (item.machine_text || '').trim()
)));
</script>

<style scoped>
.qy-review-panel { padding: .85rem; display: grid; gap: .75rem; }
.qy-review-panel h2, .qy-review-panel p { margin: 0; }
.qy-review-item { border: 1px solid var(--qy-border, #d7dde5); border-radius: .5rem; padding: .75rem; display: grid; gap: .5rem; }
.qy-review-item label { display: grid; gap: .25rem; }
.qy-review-item textarea { width: 100%; }
.qy-review-item > div { display: flex; justify-content: space-between; align-items: center; gap: .5rem; }
.qy-regenerate { justify-self: start; }
.qy-muted { color: #667085; }
</style>

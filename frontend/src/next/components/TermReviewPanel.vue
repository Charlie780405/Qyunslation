<template>
  <section class="qy-panel qy-review-panel" aria-labelledby="qy-term-review-heading">
    <header class="qy-review-panel-head">
      <div>
        <h2 id="qy-term-review-heading">术语审核</h2>
        <p>{{ unresolved }} 条待处理 · 共 {{ total }} 条</p>
      </div>
      <div class="qy-review-panel-tools">
        <button
          type="button"
          class="qy-secondary-button"
          :disabled="enriching || !items.length"
          @click="$emit('enrich')"
        >{{ enriching ? 'DeepSeek 推断中…' : 'DeepSeek 推断推荐译法' }}</button>
        <details v-if="rules?.method?.length">
          <summary>查看提取规则 {{ rules.version || '' }}</summary>
          <ul><li v-for="line in rules.method" :key="line">{{ line }}</li></ul>
        </details>
      </div>
    </header>
    <p v-if="error" class="qy-callout qy-callout-warning" role="alert">{{ error }}</p>
    <div v-if="batchEligible.length" class="qy-review-actions" aria-label="低风险术语批量操作">
      <span>已选 {{ selected.length }} 条低风险术语</span>
      <button type="button" class="qy-primary-button" :disabled="!canBatchApprove" @click="batch('approve')">批量批准</button>
      <button type="button" class="qy-secondary-button" :disabled="!selected.length" @click="batch('reject')">批量拒绝</button>
    </div>
    <p v-if="!items.length" class="qy-muted">本页暂无新术语候选。</p>
    <article v-for="item in items" :key="item.id" class="qy-review-item">
      <div class="qy-review-item-title">
        <label>
          <input
            v-if="isBatchEligible(item)"
            type="checkbox"
            :checked="selected.includes(item.id)"
            :aria-label="`选择术语 ${item.source_term}`"
            @change="toggle(item.id)"
          >
          <strong>{{ item.source_term }}</strong>
        </label>
        <span>{{ item.term_type }} · {{ item.risk }} · {{ item.status }}</span>
      </div>
      <div class="qy-term-fields">
        <span>实际译法：{{ item.observed_target || '未在译文中可靠定位' }}</span>
        <span>推荐译法：{{ item.suggested_target || '—' }}</span>
        <label>
          <span>确认译法</span>
          <input
            v-model="drafts[item.id]"
            :aria-label="`${item.source_term} 的确认译法`"
            :disabled="isFinal(item)"
          >
        </label>
      </div>
      <details v-if="item.source_context">
        <summary>上下文与提取证据（{{ item.occurrence_count || 0 }} 处）</summary>
        <p>{{ item.source_context }}</p>
        <small>{{ item.extraction_reason || '规则提取' }} · {{ item.rule_version || rules?.version }}</small>
      </details>
      <p v-if="actionHint(item)" class="qy-muted">{{ actionHint(item) }}</p>
      <div v-if="!isFinal(item)" class="qy-review-actions">
        <button
          v-if="canApprove(item)"
          type="button"
          class="qy-primary-button"
          :aria-label="`批准术语 ${item.source_term}`"
          @click="decide(item, 'approve')"
        >批准</button>
        <button
          v-if="canApprove(item)"
          type="button"
          class="qy-secondary-button"
          @click="decide(item, 'do_not_translate')"
        >不翻译</button>
        <button type="button" class="qy-secondary-button" @click="decide(item, 'reject')">拒绝</button>
        <button
          v-if="needsAdmin(item)"
          type="button"
          class="qy-secondary-button"
          @click="decide(item, 'submit_for_admin')"
        >提交术语管理员</button>
      </div>
    </article>
    <nav v-if="total > pageSize" class="qy-pagination" aria-label="术语候选分页">
      <button type="button" :disabled="page <= 1" @click="$emit('page', page - 1)">上一页</button>
      <span>第 {{ page }} 页</span>
      <button type="button" :disabled="page * pageSize >= total" @click="$emit('page', page + 1)">下一页</button>
    </nav>
  </section>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue';

const props = defineProps({
  items: { type: Array, default: () => [] },
  rules: { type: Object, default: () => ({}) },
  unresolved: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 40 },
  canManageTerms: { type: Boolean, default: false },
  error: { type: String, default: '' },
  enriching: { type: Boolean, default: false },
});
const emit = defineEmits(['decide', 'batch', 'page', 'enrich', 'error']);
const drafts = reactive({});
const selected = ref([]);
const batchEligible = computed(() => props.items.filter(isBatchEligible));
const canBatchApprove = computed(() => selected.value.length > 0 && selected.value.every((id) => (
  String(drafts[id] || '').trim()
)));

watch(() => props.items, (items) => {
  items.forEach((item) => {
    if (!(item.id in drafts)) {
      drafts[item.id] = item.confirmed_target || item.suggested_target || item.observed_target || '';
    }
  });
}, { immediate: true, deep: true });

function isFinal(item) {
  return ['approved', 'rejected', 'applied'].includes(item.status);
}

function isBatchEligible(item) {
  return item.status === 'pending' && !['high', 'critical'].includes(item.risk);
}

function isHighRisk(item) {
  return ['high', 'critical'].includes(String(item.risk || '').toLowerCase());
}

function needsAdmin(item) {
  return isHighRisk(item) && !props.canManageTerms;
}

function canApprove(item) {
  return props.canManageTerms || !isHighRisk(item);
}

function actionHint(item) {
  if (needsAdmin(item)) {
    return '高风险术语需术语管理员批准；你可拒绝或提交管理员复核。';
  }
  if (isHighRisk(item) && item.status === 'pending_admin') {
    return '已提交管理员，等待 term_admin 裁决。';
  }
  return '';
}

function resolveTarget(item, action) {
  const draft = String(drafts[item.id] || '').trim();
  const suggested = String(item.suggested_target || '').trim();
  if (draft) return draft;
  if (action === 'approve' && suggested) return suggested;
  if (action === 'do_not_translate') return item.source_term;
  return '';
}

function toggle(id) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((item) => item !== id)
    : [...selected.value, id];
}

function batch(action) {
  const byId = Object.fromEntries(props.items.map((item) => [item.id, item]));
  const decisions = selected.value.map((id) => ({
    candidate_id: id,
    action,
    expected_version: byId[id].version,
    target_term: drafts[id] || null,
    scope: 'org',
  }));
  emit('batch', decisions);
}

function decide(item, action) {
  const target = resolveTarget(item, action);
  if (action === 'approve' && !target) {
    emit('error', `「${item.source_term}」缺少确认译法：请先点击 DeepSeek 推断，或手动填写确认译法。`);
    return;
  }
  emit('decide', item, {
    action,
    expected_version: item.version,
    target_term: target || null,
    scope: 'org',
  });
}
</script>

<style scoped>
.qy-review-panel { padding: .85rem; display: grid; gap: .75rem; }
.qy-review-panel-head, .qy-review-item-title { display: flex; justify-content: space-between; gap: 1rem; align-items: start; }
.qy-review-panel-tools { display: grid; gap: .5rem; justify-items: end; }
.qy-review-panel h2, .qy-review-panel p { margin: 0; }
.qy-review-item { border: 1px solid var(--qy-border, #d7dde5); border-radius: .5rem; padding: .75rem; display: grid; gap: .65rem; }
.qy-term-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; }
.qy-term-fields label { display: grid; gap: .25rem; }
.qy-term-fields input { width: 100%; }
.qy-review-actions, .qy-pagination { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
.qy-muted { color: #667085; }
@media (max-width: 800px) { .qy-term-fields { grid-template-columns: 1fr; } }
</style>

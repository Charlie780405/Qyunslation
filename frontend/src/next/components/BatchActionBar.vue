<template>
  <section
    v-if="count > 0 || result"
    class="qy-batch-bar"
    data-batch-bar
    role="region"
    aria-label="批量操作"
  >
    <div v-if="count > 0" class="qy-batch-main">
      <div class="qy-batch-scope" data-batch-scope aria-live="polite">
        <strong>{{ scopeText }}</strong>
        <button type="button" class="qy-link-button" data-batch-clear @click="$emit('clear')">取消选择</button>
      </div>
      <div class="qy-batch-actions">
        <template v-for="name in visibleActions" :key="name">
          <button
            type="button"
            class="qy-secondary-button qy-batch-button"
            :class="{ 'qy-danger-button': ACTIONS[name].danger }"
            :data-batch-action="name"
            :disabled="busy || !availability[name].enabled"
            :aria-describedby="availability[name].enabled ? undefined : `batch-why-${name}`"
            @click="ask(name)"
          >
            {{ ACTIONS[name].label }}
          </button>
          <span v-if="!availability[name].enabled" :id="`batch-why-${name}`" class="qy-visually-hidden">{{ availability[name].reason }}</span>
        </template>
      </div>
      <p v-if="disabledReasons.length" class="qy-batch-why" data-batch-why>{{ disabledReasons.join('；') }}</p>
    </div>

    <div v-if="result" class="qy-batch-result" data-batch-result role="status" aria-live="polite">
      <p>
        <strong>{{ ACTIONS[result.action]?.label || '批量操作' }}：</strong>
        成功 {{ result.succeeded }} · 失败 {{ result.failed }} · 跳过 {{ result.skipped }}
      </p>
      <details v-if="problems.length" data-batch-details>
        <summary>查看失败与跳过的原因（{{ problems.length }}）</summary>
        <ul>
          <li v-for="item in problems" :key="item.id">
            <span class="qy-batch-outcome" :data-outcome="item.outcome">{{ item.outcome === 'failed' ? '失败' : '跳过' }}</span>
            {{ item.name || item.id.slice(0, 8) }} — {{ item.message || item.reason_code }}
          </li>
        </ul>
      </details>
      <div class="qy-batch-result-actions">
        <button v-if="result.failed" type="button" class="qy-secondary-button" data-batch-retry :disabled="busy" @click="$emit('retry-failed')">重试失败项（{{ result.failed }}）</button>
        <button type="button" class="qy-link-button" data-batch-dismiss @click="$emit('dismiss-result')">关闭</button>
      </div>
    </div>

    <div v-if="pending" class="qy-drawer-backdrop" @click.self="cancel">
      <div
        ref="dialogEl"
        class="qy-batch-confirm"
        data-batch-confirm
        role="alertdialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        :aria-describedby="bodyId"
        tabindex="-1"
        @keydown="onKeydown"
      >
        <h2 :id="titleId">{{ confirmTitle }}</h2>
        <div :id="bodyId">
          <p>{{ confirmBody }}</p>
          <p v-if="skipText" data-batch-skip class="qy-muted">预计会跳过 {{ skippedRows.length }} 个：{{ skipText }}。</p>
          <label v-if="ACTIONS[pending].typed" class="qy-field">
            <span>此操作不可撤销。请输入任务数量 <strong>{{ count }}</strong> 以确认：</span>
            <input v-model="typed" class="qy-input" data-batch-typed inputmode="numeric" autocomplete="off" />
          </label>
        </div>
        <div class="qy-batch-confirm-actions">
          <button type="button" class="qy-secondary-button" data-batch-cancel @click="cancel">取消</button>
          <button
            type="button"
            class="qy-primary-button"
            :class="{ 'qy-danger-button': ACTIONS[pending].danger }"
            data-batch-confirm-go
            :disabled="!canConfirm"
            @click="go"
          >
            {{ ACTIONS[pending].label }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue';
import { lifecycleLabel } from '../labels.js';

// What each batch action is called, what the server calls it in `allowed_actions`, and where it applies.
const ACTIONS = {
  archive: { label: '归档', allowed: 'archive', scope: 'active', danger: false, typed: false },
  unarchive: { label: '取消归档', allowed: 'restore', scope: 'active', danger: false, typed: false },
  trash: { label: '移入回收站', allowed: 'delete', scope: 'active', danger: true, typed: false },
  restore_from_trash: { label: '恢复', allowed: 'restore_from_trash', scope: 'trash', danger: false, typed: false },
  purge: { label: '永久清除', allowed: 'purge', scope: 'trash', danger: true, typed: true },
};

const props = defineProps({
  count: { type: Number, default: 0 },
  rows: { type: Array, default: () => [] }, // the selected rows that are loaded on this page
  allMatching: { type: Boolean, default: false },
  excludedCount: { type: Number, default: 0 },
  inTrash: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  result: { type: Object, default: null },
});
const emit = defineEmits(['run', 'clear', 'retry-failed', 'dismiss-result']);

const uid = Math.random().toString(36).slice(2, 8);
const titleId = `batch-title-${uid}`;
const bodyId = `batch-body-${uid}`;
const pending = ref('');
const typed = ref('');
const dialogEl = ref(null);
let opener = null;

const visibleActions = computed(() => Object.keys(ACTIONS).filter((name) => ACTIONS[name].scope === (props.inTrash ? 'trash' : 'active')));

const scopeText = computed(() => {
  if (props.allMatching) {
    return props.excludedCount
      ? `已选择全部筛选结果（排除 ${props.excludedCount} 项，共 ${props.count} 项）`
      : `已选择全部 ${props.count} 条筛选结果`;
  }
  return `已选择 ${props.count} 项`;
});

function eligible(name) {
  return props.rows.filter((row) => Array.isArray(row.allowed_actions) && row.allowed_actions.includes(ACTIONS[name].allowed));
}

// An action is on when at least one selected task can take it (the server re-checks every task).
// With "all matches" only the loaded rows are known, so the server decides.
const availability = computed(() => {
  const out = {};
  for (const name of visibleActions.value) {
    const unknown = props.allMatching && props.rows.length < props.count;
    const ok = eligible(name).length > 0 || unknown;
    out[name] = { enabled: ok, reason: ok ? '' : reasonFor(name) };
  }
  return out;
});

function groupsOf(rows) {
  const tally = new Map();
  for (const row of rows) tally.set(lifecycleLabel(row), (tally.get(lifecycleLabel(row)) || 0) + 1);
  return [...tally].map(([label, n]) => `${label} ${n}`).join('、');
}

function reasonFor(name) {
  const why = groupsOf(props.rows);
  return `所选任务当前都不能“${ACTIONS[name].label}”${why ? `（${why}）` : ''}`;
}

const disabledReasons = computed(() => visibleActions.value
  .filter((name) => !availability.value[name].enabled)
  .map((name) => availability.value[name].reason));

const skippedRows = computed(() => (pending.value ? props.rows.filter((row) => !eligible(pending.value).includes(row)) : []));
const skipText = computed(() => (skippedRows.value.length ? groupsOf(skippedRows.value) : ''));

const confirmTitle = computed(() => (pending.value ? `${ACTIONS[pending.value].label} ${props.count} 个任务？` : ''));
const confirmBody = computed(() => ({
  archive: '归档的任务仍可在“已归档”中找到，随时取消归档。',
  unarchive: '这些任务会回到任务列表。',
  trash: '任务会移入回收站，保留 30 天，期间可以恢复；到期前不会删除任何文件。',
  restore_from_trash: '这些任务会回到任务列表。',
  purge: '任务及其文件、产物会被永久删除。审核决定会保留在审计记录里。',
}[pending.value] || ''));

const canConfirm = computed(() => !props.busy && (!pending.value || !ACTIONS[pending.value].typed || typed.value.trim() === String(props.count)));

const problems = computed(() => (props.result?.items || []).filter((item) => item.outcome !== 'succeeded'));

async function ask(name) {
  opener = document.activeElement;
  typed.value = '';
  pending.value = name;
  await nextTick();
  dialogEl.value?.focus();
}

function cancel() {
  pending.value = '';
  opener?.focus?.();
}

function go() {
  if (!canConfirm.value) return;
  const action = pending.value;
  pending.value = '';
  emit('run', action);
  nextTick(() => opener?.isConnected && opener.focus?.());
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.stopPropagation();
    cancel();
    return;
  }
  if (event.key !== 'Tab' || !dialogEl.value) return;
  const focusable = [...dialogEl.value.querySelectorAll('button, input, [tabindex]:not([tabindex="-1"])')].filter((el) => !el.disabled);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogEl.value)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

onBeforeUnmount(() => { pending.value = ''; });

// Lets a row's own "permanently remove" button open the same confirmation.
defineExpose({ ask });
</script>

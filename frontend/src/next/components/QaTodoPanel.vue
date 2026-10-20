<template>
  <section class="qy-panel qy-qa-panel" aria-labelledby="qy-qa-todo-heading" data-qa-panel>
    <header class="qy-qa-panel-head">
      <div>
        <h2 id="qy-qa-todo-heading">质量问题 <small>（{{ openItems.length }} 项待处理）</small></h2>
        <p v-if="nextStep" class="qy-qa-next" data-next-step><strong>下一步：</strong>{{ nextStep }}</p>
      </div>
      <div class="qy-qa-panel-actions">
        <button
          v-if="canRevise"
          class="qy-secondary-button"
          type="button"
          :disabled="Boolean(busy)"
          @click="$emit('revise')"
        >生成修订版</button>
      </div>
    </header>

    <ul class="qy-delivery-checklist" aria-label="交付清单">
      <li v-for="row in checklist" :key="row.key" :data-state="row.ok ? 'ok' : 'todo'">
        <span class="qy-check-mark" aria-hidden="true">{{ row.ok ? '✓' : '!' }}</span>
        <span class="qy-check-label">{{ row.label }}</span>
        <span class="qy-check-value">{{ row.value }}</span>
        <span class="qy-visually-hidden">{{ row.ok ? '已满足' : '待处理' }}</span>
      </li>
    </ul>

    <p v-if="checkLine" class="qy-qa-check" data-qa-check>{{ checkLine }}</p>

    <p v-if="notice" class="qy-qa-notice" role="status">{{ notice }}</p>
    <p v-if="error" class="qy-qa-error" role="alert">{{ error }}</p>

    <div class="qy-qa-filters" role="group" aria-label="筛选质量问题">
      <button
        v-for="option in filters"
        :key="option.key"
        type="button"
        class="qy-link-button"
        :aria-pressed="filter === option.key"
        @click="filter = option.key"
      >{{ option.label }}（{{ option.count }}）</button>
    </div>

    <p v-if="carryOverItems.length" class="qy-qa-carry" data-qa-carry-over>
      <button type="button" class="qy-remedy-btn is-primary" :disabled="Boolean(busy) || submitting" @click="carryOverAll">
        沿用上一版的全部结论（{{ carryOverItems.length }} 项）
      </button>
      <span class="qy-muted">上一版已经处理过、这一版原样再次出现的问题，一键按上一版的结论和理由再确认一次；每一项仍是单独的、记入审计的处置。</span>
    </p>

    <p v-if="batchGroups.length && !batchCode" class="qy-qa-batch-entry">
      <button
        v-for="group in batchGroups"
        :key="group.code"
        type="button"
        class="qy-link-button"
        @click="startBatch(group)"
      >批量处理：{{ group.title }}（{{ group.items.length }} 项）</button>
    </p>

    <section v-if="batchCode" class="qy-qa-batch" data-qa-batch aria-label="批量处理">
      <h3>批量处理：{{ batchGroup?.title }}</h3>
      <p class="qy-muted">只会处理你勾选的项目，默认不选中任何一项；每一项都会单独校验权限和状态。</p>
      <ul>
        <li v-for="entry in batchGroup?.items || []" :key="entry.id">
          <label>
            <input v-model="batchSelected" type="checkbox" :value="entry.id" />
            <span>{{ locationSummary(entry) }}</span>
          </label>
        </li>
      </ul>
      <label class="qy-field">
        <span>处理方式</span>
        <select v-model="batchAction">
          <option v-for="action in batchActions" :key="action" :value="action">{{ actionLabel(action) }}</option>
        </select>
      </label>
      <label class="qy-field">
        <span>理由（至少 10 个字，将记入审计）</span>
        <textarea v-model="batchReason" rows="2" />
      </label>
      <ul v-if="batchResults.length" class="qy-qa-batch-results" aria-live="polite">
        <li v-for="result in batchResults" :key="result.item_id" :data-outcome="result.outcome">
          {{ result.outcome === 'succeeded' ? '成功' : '失败' }}：{{ result.message || result.item_id }}
        </li>
      </ul>
      <div class="qy-qa-form-actions">
        <button
          type="button"
          class="qy-primary-button"
          :disabled="!canSubmitBatch || submitting"
          @click="submitBatch"
        >{{ submitting ? '提交中…' : '提交' }}</button>
        <button type="button" class="qy-secondary-button" @click="cancelBatch">取消</button>
      </div>
    </section>

    <ul v-if="visibleItems.length" class="qy-qa-list">
      <li v-for="entry in visibleItems" :key="entry.id" :data-severity="entry.severity" :data-status="entry.status || 'open'">
        <button
          type="button"
          class="qy-qa-item"
          :aria-pressed="selectedId === keyOf(entry)"
          :aria-label="`质量问题（${severityLabel(entry.severity)}）：${entry.title || entry.message}`"
          @click="$emit('select', selectedId === keyOf(entry) ? '' : keyOf(entry))"
        >
          <strong>{{ severityLabel(entry.severity) }}</strong>
          <span v-if="ruleClassLabel(entry.rule_class)" class="qy-qa-class">{{ ruleClassLabel(entry.rule_class) }}</span>
          <span class="qy-qa-message">{{ entry.title || entry.message }}</span>
          <span class="qy-qa-where">{{ locationSummary(entry) }}</span>
          <em v-if="entry.status && entry.status !== 'open'" class="qy-qa-status">{{ itemStatusLabel(entry.status) }}</em>
        </button>
      </li>
    </ul>
    <p v-else class="qy-muted">{{ emptyText }}</p>

    <section v-if="selected" class="qy-qa-detail" data-qa-detail aria-live="polite">
      <h3>
        {{ selected.title || selected.message }}
        <span v-if="ruleClassLabel(selected.rule_class)" class="qy-qa-class">{{ ruleClassLabel(selected.rule_class) }}</span>
        <span class="qy-qa-status">{{ itemStatusLabel(selected.status) }}</span>
      </h3>
      <dl class="qy-qa-detail-fields">
        <dt>哪里有问题</dt>
        <dd>
          <ul v-if="anchorsOf(selected).length" class="qy-anchor-list">
            <li v-for="(anchor, index) in anchorsOf(selected)" :key="index">
              <strong>{{ anchorText(anchor) }}</strong>
              <span v-if="anchor.label"> · {{ anchor.label }}</span>
              <blockquote v-if="anchor.excerpt">{{ anchor.excerpt }}</blockquote>
              <button
                v-if="anchor.page"
                type="button"
                class="qy-link-button"
                @click="$emit('locate', anchor)"
              >在对照视图定位</button>
            </li>
          </ul>
          <p v-else>{{ selected.location?.unlocatable_reason || '检查没有返回具体位置' }}</p>
        </dd>
        <dt>为什么影响交付</dt>
        <dd>{{ selected.severity === 'info' ? '不影响交付，仅作审计记录。' : (selected.why || selected.message) }}</dd>
        <dt>怎么处理</dt>
        <dd>{{ selected.severity === 'info' ? '无需处理。' : (selected.how || '请联系管理员查看该检查项。') }}</dd>
      </dl>
      <p v-if="selected.rule_class === 'C1'" class="qy-qa-critical-note">
        关键事实类问题不能直接放行：请修复后生成修订版；如果确认是检查规则误判，请反馈误报，由有确认权限的人（术语管理员、管理员、所有者）确认。
      </p>
      <p v-if="selected.prior_version_disposition" class="qy-qa-prior-note">
        上一版本曾授权例外（{{ selected.prior_version_disposition.actor_sub }}：{{ selected.prior_version_disposition.reason }}）。
        本版本的输出不同，例外不会沿用，需要重新处置。
      </p>
      <details v-if="selected.evidence && Object.keys(selected.evidence).length">
        <summary>技术详情</summary>
        <p class="qy-muted">检查项 {{ selected.code }} · {{ selected.message }}</p>
        <pre>{{ JSON.stringify(selected.evidence, null, 2) }}</pre>
      </details>
      <section v-if="selected.history?.length" class="qy-qa-history" aria-label="处置记录">
        <h4>处置记录</h4>
        <ol>
          <li v-for="entry in selected.history" :key="entry.id">
            {{ actionLabel(entry.action) }} · {{ entry.actor_sub }}<template v-if="entry.self_review">（提交人自审）</template>：{{ entry.reason }}
          </li>
        </ol>
      </section>

      <section class="qy-qa-remedies" data-qa-remedies aria-label="解决方案">
        <h4>怎么解决</h4>
        <p v-if="selected.severity === 'info'" class="qy-muted" data-qa-info-note>
          这是检查记录，不影响交付，无需处理。
        </p>
        <template v-else-if="remedies.length || infoRemedies.length">
          <p v-for="info in infoRemedies" :key="info.id" class="qy-remedy-info" data-remedy-info>
            <strong>{{ info.label }}</strong>
            <span>{{ info.why }}</span>
          </p>
          <div v-if="remedies.length" class="qy-remedy-row" role="group" aria-label="可选的解决方式">
            <button
              v-for="remedy in remedies"
              :key="remedy.id"
              type="button"
              class="qy-remedy-btn"
              :class="{ 'is-primary': remedy.recommended }"
              :disabled="Boolean(busy) || submitting"
              :data-remedy="remedy.id"
              :aria-describedby="hintId"
              @click="runRemedy(remedy)"
              @mouseenter="hinted = remedy.id"
              @mouseleave="hinted = ''"
              @focus="hinted = remedy.id"
              @blur="hinted = ''"
            >{{ remedy.label }}<span v-if="remedy.recommended" class="qy-remedy-tag">推荐</span></button>
          </div>
          <p v-if="hintRemedy" :id="hintId" class="qy-remedy-hint" data-remedy-hint>{{ hintRemedy.why }}</p>
        </template>
        <p v-else class="qy-muted" data-qa-no-remedy>
          当前账号对这一项没有可执行的操作。请联系有复核权限的同事（复核人、术语管理员、管理员或所有者）处理。
        </p>
      </section>

      <form v-if="activeAction" class="qy-qa-form" data-qa-form @submit.prevent="submitForm">
        <p class="qy-muted">{{ activeThen ? '提交后会依次记录“反馈误报”和“确认误报”，两条记录都会进入审计。' : ACTION_HELP[activeAction] }}</p>
        <label class="qy-field">
          <span>理由（至少 10 个字，将记入审计）</span>
          <textarea v-model="reason" rows="3" />
        </label>
        <div class="qy-qa-form-actions">
          <button type="submit" class="qy-primary-button" :disabled="!canSubmit || submitting">{{ submitting ? '提交中…' : '提交' }}</button>
          <button type="button" class="qy-secondary-button" @click="closeForm">取消</button>
        </div>
      </form>

      <details v-if="selected.allowed_dispositions?.length" class="qy-qa-more" data-qa-more>
        <summary>更多处置方式</summary>
        <div class="qy-qa-actions" data-qa-actions>
          <button
            v-for="action in selected.allowed_dispositions"
            :key="action"
            type="button"
            class="qy-secondary-button"
            :disabled="Boolean(busy) || submitting"
            :aria-pressed="activeAction === action"
            @click="openForm(action)"
          >{{ actionLabel(action) }}</button>
        </div>
      </details>
    </section>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import {
  ACTION_HELP,
  GATE_REASON_LABELS,
  actionLabel,
  anchorText,
  can,
  isInfoItem,
  isOpenItem,
  itemStatusLabel,
  lifecycleOf,
  ruleClassLabel,
  severityLabel,
  sortItems,
  termsBlockDelivery,
} from '../labels.js';

const props = defineProps({
  run: { type: Object, default: null },
  items: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  busy: { type: String, default: '' },
  onDispose: { type: Function, default: null },
  onBatch: { type: Function, default: null },
});
const emit = defineEmits(['select', 'locate', 'revise', 'recheck', 'termbase']);

const filter = ref('open');
const activeAction = ref('');
const activeThen = ref('');
const hinted = ref('');
const hintId = `qy-remedy-hint-${Math.random().toString(36).slice(2, 8)}`;
const reason = ref('');
const submitting = ref(false);
const error = ref('');
const notice = ref('');
const batchCode = ref('');
const batchSelected = ref([]);
const batchAction = ref('acknowledge');
const batchReason = ref('');
const batchResults = ref([]);

const keyOf = (entry) => entry.object_id || `qa:${entry.id}`;
const anchorsOf = (entry) => entry.location?.anchors || [];
const locationSummary = (entry) => {
  const first = anchorsOf(entry)[0];
  return first ? anchorText(first) : '位置未知';
};

const currentItems = computed(() => props.items.filter((entry) => entry.is_current !== false));
const openItems = computed(() => currentItems.value.filter(isOpenItem));
const closedItems = computed(() => currentItems.value.filter((entry) => !isOpenItem(entry) && !isInfoItem(entry)));
const filters = computed(() => [
  { key: 'open', label: '未处理', count: openItems.value.length },
  { key: 'closed', label: '已处理', count: closedItems.value.length },
  { key: 'all', label: '全部', count: currentItems.value.length },
]);
const visibleItems = computed(() => sortItems(
  filter.value === 'open' ? openItems.value : filter.value === 'closed' ? closedItems.value : currentItems.value,
));
const emptyText = computed(() => (
  filter.value === 'open' ? '没有待处理的质量问题。' : filter.value === 'closed' ? '还没有已处理的问题。' : '本次检查没有发现问题。'
));
const selected = computed(() => currentItems.value.find((entry) => keyOf(entry) === props.selectedId) || null);

const canRevise = computed(() => Boolean(props.run) && can(props.run, 'revise')
  && ['qa_action', 'qa_unavailable', 'review', 'changes_requested', 'completed'].includes(lifecycleOf(props.run)));

const nextStep = computed(() => {
  const run = props.run;
  if (!run) return '';
  const pending = run.pending_counts || {};
  switch (run.next_action) {
    case 'fix_quality_issues':
      return `处理 ${pending.qa_blockers || 0} 个阻断问题：对照问题处的原文和译文核对，修正后点击“生成修订版”；确认是检查误判或可例外时，逐项写明理由处置。`;
    case 'retry_qa':
      return '质量检查服务当时无法运行（不代表译文有问题）。服务恢复后点击上方的“重新检查”。';
    case 'review':
      return '检查已通过，请人工复核并批准正式稿。';
    case 'resolve_gate_items':
      return `正式稿还差：${(run.formal_gate?.reasons || []).map((r) => GATE_REASON_LABELS[r] || r).join('、')}。`;
    case 'create_revision':
      return '本版本已被退回：请根据复核意见生成修订版。';
    default:
      return '';
  }
});

const checklist = computed(() => {
  const run = props.run;
  if (!run) return [];
  const pending = run.pending_counts || {};
  const gate = run.formal_gate || {};
  const approved = run.quality_state === 'approved';
  const rows = [
    { key: 'blockers', label: '阻断问题', value: `${pending.qa_blockers || 0} 项待处理`, ok: !pending.qa_blockers },
  ];
  if (pending.qa_unavailable) {
    rows.push({ key: 'unavailable', label: '检查未完成', value: `${pending.qa_unavailable} 项`, ok: false });
  }
  rows.push(
    termsBlockDelivery(run)
      ? { key: 'terms', label: '待审核术语', value: `${pending.unresolved_terms || 0} 条`, ok: !pending.unresolved_terms }
      : { key: 'terms', label: '词库待整理（不影响交付）', value: `${pending.unresolved_terms || 0} 条`, ok: true },
    { key: 'version', label: '版本', value: run.superseded_by ? '已被更新版本取代' : '当前最新', ok: !run.superseded_by },
  );
  const reasons = (gate.reasons || []).map((r) => GATE_REASON_LABELS[r] || r);
  rows.push({
    key: 'formal',
    label: '正式稿',
    value: approved ? '已解锁' : `未解锁${reasons.length ? `：${reasons.join('、')}` : ''}`,
    ok: approved,
  });
  return rows;
});

const checkLine = computed(() => {
  const check = props.run?.qa_check;
  if (!check?.round_no) return '';
  const parts = [`第 ${check.round_no} 轮检查`];
  const diff = check.diff;
  if (diff?.baseline) {
    parts.push(`${diff.baseline === 'previous_version' ? '对比上一版本：' : ''}新增 ${diff.new}、已解决 ${diff.resolved}、仍存在 ${diff.persisting}`);
  }
  if (check.rule_set_version) parts.push(`规则集 ${check.rule_set_version}`);
  return parts.join(' · ');
});

// ---- carry the previous version's conclusions over, in one go --------------------------------
const carryRemedyOf = (entry) => (entry.remedies || []).find((remedy) => remedy.id === 'carry_over');
const carryOverItems = computed(() => openItems.value.filter((entry) => carryRemedyOf(entry)));

async function carryOverAll() {
  if (submitting.value || !props.onDispose) return;
  submitting.value = true;
  error.value = '';
  notice.value = '';
  let done = 0;
  try {
    for (const entry of [...carryOverItems.value]) {
      const remedy = carryRemedyOf(entry);
      for (const step of [remedy.action, remedy.then].filter(Boolean)) {
        await props.onDispose(entry, step, remedy.reason);
      }
      done += 1;
    }
    notice.value = `已沿用上一版的结论：${done} 项`;
  } catch (failure) {
    error.value = `${done ? `已处理 ${done} 项，` : ''}在下一项停下：${failure?.message || '处置失败，请稍后重试'}`;
  } finally {
    submitting.value = false;
  }
}

// ---- remedies: concrete ways out of the selected problem ------------------------------------
// The server proposes them per problem and per person; here only the ones that can run in this task state stay.
const allRemedies = computed(() => (selected.value?.remedies || []).filter((remedy) => {
  if (remedy.kind === 'revise') return canRevise.value;
  if (remedy.kind === 'recheck') return Boolean(props.run) && can(props.run, 'requalify');
  if (remedy.kind === 'locate') return anchorsOf(selected.value).some((anchor) => anchor.page);
  return true;
}));
const remedies = computed(() => allRemedies.value.filter((remedy) => remedy.kind !== 'info'));
const infoRemedies = computed(() => allRemedies.value.filter((remedy) => remedy.kind === 'info'));
// One line of explanation under the row: the option under the pointer or focus, else the recommended one.
const hintRemedy = computed(() => remedies.value.find((remedy) => remedy.id === hinted.value)
  || remedies.value.find((remedy) => remedy.recommended)
  || remedies.value[0]
  || null);

function runRemedy(remedy) {
  switch (remedy.kind) {
    case 'revise':
      emit('revise');
      break;
    case 'recheck':
      emit('recheck');
      break;
    case 'termbase':
      emit('termbase', remedy.search || '');
      break;
    case 'locate':
      emit('locate', anchorsOf(selected.value).find((anchor) => anchor.page));
      break;
    case 'disposition':
      // Open the normal form with the reason already filled in: one check, one click, and it stays editable.
      openForm(remedy.action);
      reason.value = remedy.reason || '';
      activeThen.value = remedy.then || '';
      break;
    default:
      break;
  }
}

// ---- single disposition ---------------------------------------------------------------------
const canSubmit = computed(() => reason.value.trim().length >= 10);

function openForm(action) {
  activeAction.value = action;
  activeThen.value = '';
  reason.value = '';
  error.value = '';
  notice.value = '';
}

function closeForm() {
  activeAction.value = '';
  activeThen.value = '';
  reason.value = '';
}

async function submitForm() {
  if (!canSubmit.value || submitting.value || !selected.value || !props.onDispose) return;
  submitting.value = true;
  error.value = '';
  try {
    const text = reason.value.trim();
    const steps = activeThen.value ? [activeAction.value, activeThen.value] : [activeAction.value];
    // "report, then confirm" for someone who may confirm: each step is its own audited record, and a failure
    // in the second leaves the first in place, now shown as a pending report with its next step.
    for (const step of steps) await props.onDispose(selected.value, step, text);
    notice.value = `已记录：${steps.map(actionLabel).join('、')}`;
    closeForm();
  } catch (failure) {
    error.value = failure?.message || '处置失败，请稍后重试';
  } finally {
    submitting.value = false;
  }
}

// ---- batch ---------------------------------------------------------------------------------------
const batchGroups = computed(() => {
  const groups = new Map();
  for (const entry of openItems.value) {
    if (!entry.batchable) continue;
    if (!groups.has(entry.code)) groups.set(entry.code, { code: entry.code, title: entry.title || entry.code, items: [] });
    groups.get(entry.code).items.push(entry);
  }
  return [...groups.values()].filter((group) => group.items.length >= 2);
});
const batchGroup = computed(() => batchGroups.value.find((group) => group.code === batchCode.value) || null);
const batchActions = computed(() => {
  const group = batchGroup.value;
  if (!group) return [];
  const common = group.items
    .map((entry) => entry.allowed_dispositions || [])
    .reduce((acc, list) => acc.filter((action) => list.includes(action)));
  return common.filter((action) => ['acknowledge', 'grant_waiver'].includes(action));
});
const canSubmitBatch = computed(() => batchSelected.value.length > 0
  && batchReason.value.trim().length >= 10 && batchActions.value.includes(batchAction.value));

function startBatch(group) {
  batchCode.value = group.code;
  batchSelected.value = []; // never pre-select: the person chooses what to handle
  batchResults.value = [];
  batchReason.value = '';
  batchAction.value = 'acknowledge';
  error.value = '';
  notice.value = '';
}

function cancelBatch() {
  batchCode.value = '';
  batchSelected.value = [];
  batchResults.value = [];
}

async function submitBatch() {
  if (!canSubmitBatch.value || submitting.value || !props.onBatch) return;
  submitting.value = true;
  error.value = '';
  try {
    const response = await props.onBatch({
      action: batchAction.value,
      reason: batchReason.value.trim(),
      item_ids: [...batchSelected.value],
    });
    batchResults.value = response?.results || [];
    const failed = batchResults.value.filter((result) => result.outcome !== 'succeeded');
    if (failed.length) {
      batchSelected.value = failed.map((result) => result.item_id); // retry only what failed
    } else {
      notice.value = `已记录：批量${actionLabel(batchAction.value)} ${batchResults.value.length} 项`;
      cancelBatch();
    }
  } catch (failure) {
    error.value = failure?.message || '批量处理失败，请稍后重试';
  } finally {
    submitting.value = false;
  }
}

watch(() => props.selectedId, () => {
  closeForm();
  error.value = '';
});
</script>

<style scoped>
.qy-qa-panel { display: grid; gap: .75rem; min-width: 0; padding: .9rem; }
.qy-qa-panel-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; flex-wrap: wrap; }
.qy-qa-panel h2 { margin: 0; font-size: 1.05rem; }
.qy-qa-next { margin: .35rem 0 0; }
.qy-delivery-checklist { list-style: none; display: grid; gap: .25rem; margin: 0; padding: 0; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
.qy-delivery-checklist li { display: flex; gap: .4rem; align-items: baseline; padding: .35rem .5rem; border: 1px solid var(--qy-border, #d6dce3); }
.qy-delivery-checklist li[data-state='todo'] { border-color: #b45309; background: #fffbeb; }
.qy-delivery-checklist li[data-state='ok'] { border-color: #86b79a; }
.qy-check-mark { font-weight: 700; }
.qy-check-value { margin-left: auto; text-align: right; color: #2d3744; }
.qy-qa-check { margin: 0; color: #3b4452; font-size: .85rem; }
.qy-qa-notice { margin: 0; color: #1c6b3a; }
.qy-qa-error { margin: 0; color: #8b1e1e; }
.qy-qa-filters { display: flex; gap: .5rem; flex-wrap: wrap; }
.qy-qa-filters [aria-pressed='true'] { font-weight: 700; text-decoration: underline; }
.qy-qa-list { list-style: none; padding: 0; margin: 0; display: grid; gap: .4rem; }
.qy-qa-item { width: 100%; display: flex; flex-wrap: wrap; gap: .4rem .6rem; text-align: left; padding: .5rem .65rem; border: 1px solid var(--qy-border, #d6dce3); background: #fff; cursor: pointer; min-height: 44px; }
.qy-qa-item[aria-pressed='true'] { border-color: #1f3a5f; box-shadow: inset 3px 0 0 #1f3a5f; background: #f1f6fb; }
li[data-severity='blocker'] .qy-qa-item strong { color: #8b1e1e; }
li[data-severity='unavailable'] .qy-qa-item strong { color: #7a5200; }
.qy-qa-class, .qy-qa-status { font-size: .78rem; padding: 0 .35rem; border: 1px solid currentColor; color: #3b4452; }
.qy-qa-message { flex: 1 1 14rem; color: #1b2430; }
.qy-qa-where { color: #5b6573; font-size: .85rem; }
.qy-qa-detail { border-top: 1px solid var(--qy-border, #d6dce3); padding-top: .75rem; display: grid; gap: .6rem; }
.qy-qa-detail h3 { margin: 0; font-size: 1rem; display: flex; gap: .5rem; flex-wrap: wrap; align-items: baseline; }
.qy-qa-detail-fields { display: grid; grid-template-columns: max-content 1fr; gap: .35rem .9rem; margin: 0; }
.qy-qa-detail-fields dt { color: #3b4452; font-weight: 600; }
.qy-qa-detail-fields dd { margin: 0; overflow-wrap: anywhere; }
.qy-qa-remedies { margin: .75rem 0; padding: .55rem .75rem .6rem; border: 1px solid #c9d7e6; border-radius: 6px; background: #f4f8fc; }
.qy-qa-remedies h4 { margin: 0 0 .45rem; font-size: .85rem; letter-spacing: .02em; color: #3b4452; }
.qy-remedy-row { display: flex; flex-wrap: wrap; gap: .45rem .5rem; align-items: center; }
.qy-remedy-btn { display: inline-flex; align-items: center; gap: .4rem; width: auto; min-height: 2.25rem; padding: .3rem .85rem; font: inherit; font-size: .9rem; line-height: 1.2; color: #005076; background: #fff; border: 1px solid #9fb3c8; border-radius: 999px; cursor: pointer; }
.qy-remedy-btn:hover:not(:disabled) { border-color: #005076; background: #eef5fa; }
.qy-remedy-btn:focus-visible { outline: 3px solid #f2a900; outline-offset: 2px; }
.qy-remedy-btn:disabled { opacity: .55; cursor: not-allowed; }
.qy-remedy-btn.is-primary { color: #fff; background: #005076; border-color: #005076; font-weight: 600; }
.qy-remedy-btn.is-primary:hover:not(:disabled) { background: #003f5c; }
.qy-remedy-tag { padding: 0 .4rem; font-size: .7rem; font-weight: 600; color: #005076; background: #fff; border-radius: 999px; }
.qy-remedy-hint { margin: .5rem 0 0; font-size: .85rem; color: #3b4452; min-height: 1.3em; }
.qy-remedy-info { display: grid; gap: .1rem; margin: 0 0 .5rem; padding: .35rem .6rem; font-size: .85rem; background: #fff8e6; border-left: 3px solid #d97706; }
.qy-qa-carry { display: flex; flex-wrap: wrap; gap: .5rem .75rem; align-items: center; margin: .5rem 0; }
.qy-qa-more { margin-top: .6rem; }
.qy-qa-more > summary { cursor: pointer; font-size: .85rem; color: #4a5565; }
.qy-qa-more .qy-qa-actions { margin-top: .4rem; display: flex; flex-wrap: wrap; gap: .4rem; }
@media (max-width: 640px) { .qy-remedy-btn { min-height: 2.75rem; } }
.qy-anchor-list { list-style: none; padding: 0; margin: 0; display: grid; gap: .4rem; }
.qy-anchor-list blockquote { margin: .2rem 0; padding: .25rem .6rem; border-left: 3px solid #9fb3c8; background: #f6f8fa; font-size: .9rem; }
.qy-qa-critical-note { margin: 0; padding: .5rem .7rem; background: #fef2f2; border-left: 4px solid #8b1e1e; }
.qy-qa-prior-note { margin: 0; padding: .5rem .7rem; background: #fffbeb; border-left: 4px solid #b45309; }
.qy-qa-history ol { margin: 0; padding-left: 1.2rem; }
.qy-qa-actions { display: flex; gap: .5rem; flex-wrap: wrap; }
.qy-qa-form, .qy-qa-batch { display: grid; gap: .5rem; padding: .6rem; border: 1px solid var(--qy-border, #d6dce3); background: #f8fafc; }
.qy-qa-form textarea, .qy-qa-batch textarea { width: 100%; }
.qy-qa-form-actions { display: flex; gap: .5rem; }
.qy-qa-batch ul { list-style: none; padding: 0; margin: 0; display: grid; gap: .25rem; }
.qy-qa-batch-results [data-outcome='failed'] { color: #8b1e1e; }
@media (max-width: 700px) {
  .qy-qa-detail-fields { grid-template-columns: 1fr; }
}
</style>
